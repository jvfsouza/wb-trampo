"""Leitura do config.toml."""

from __future__ import annotations

import sqlite3
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path


@dataclass
class Limites:
    max_vagas_por_busca: int = 100
    pausa_min_s: float = 2.0  # sites em geral (Gupy)
    pausa_max_s: float = 5.0
    pausa_linkedin_min_s: float = 8.0  # o LinkedIn é o que mais bloqueia
    pausa_linkedin_max_s: float = 15.0
    max_requisicoes: int = 200  # por execução; 0 = sem teto
    intervalo_minimo_min: float = 30  # entre execuções; 0 = desliga
    buscar_descricao: bool = True


@dataclass
class Busca:
    palavra_chave: str
    local: str = ""
    modalidade: list[str] = field(default_factory=list)
    nivel: list[str] = field(default_factory=list)
    publicada: str | int | None = None  # segundos (86400) ou atalho ("24h", "semana", "mes")
    site: str = "linkedin"  # no config.toml o campo é obrigatório

    def __post_init__(self) -> None:
        self.site = str(self.site).strip().lower()
        # aceita tanto "remoto" quanto ["remoto"] no TOML
        if isinstance(self.modalidade, str):
            self.modalidade = [self.modalidade]
        if isinstance(self.nivel, str):
            self.nivel = [self.nivel]


@dataclass
class GoogleSheets:
    """Lido de google_sheets.toml (fica fora do git: tem a senha e o link do script)."""

    url_script: str  # "URL do app da Web" do Apps Script (termina em /exec)
    senha: str  # a mesma SENHA escrita no Apps Script


ARQUIVO_SHEETS = "google_sheets.toml"


@dataclass
class FiltroSheets:
    """Lido de filtro_sheets.toml. Condição SQL (trecho do WHERE) sobre a tabela vagas.
    Vazia (ou sem o arquivo) = envia todas as vagas novas."""

    filtro_sql: str = ""


ARQUIVO_FILTRO = "filtro_sheets.toml"


@dataclass
class Config:
    buscas: list[Busca]
    limites: Limites
    google_sheets: GoogleSheets | None = None
    filtro_sheets: FiltroSheets = field(default_factory=FiltroSheets)


def _checar_campos(dados: dict, classe: type, onde: str) -> None:
    aceitos = [f.name for f in fields(classe)]
    for campo in dados:
        if campo not in aceitos:
            raise ValueError(
                f"{onde}: campo desconhecido {campo!r}. Campos aceitos: {', '.join(aceitos)}"
            )
    obrigatorios = {Busca: ("site", "palavra_chave"), GoogleSheets: ("url_script", "senha")}
    for obrigatorio in obrigatorios.get(classe, ()):
        if obrigatorio not in dados:
            raise ValueError(f"{onde}: falta o campo '{obrigatorio}'")


def _validar_site(busca: Busca, onde: str) -> None:
    from .fontes import FONTES, NAO_SUPORTADOS  # import aqui evita import circular

    if busca.site in NAO_SUPORTADOS:
        raise ValueError(f"{onde}: site {busca.site!r} não é suportado: {NAO_SUPORTADOS[busca.site]}")
    if busca.site not in FONTES:
        raise ValueError(
            f"{onde}: site desconhecido {busca.site!r}. Use um de: {', '.join(FONTES)}"
        )
    try:
        FONTES[busca.site].validar(busca)
    except ValueError as erro:
        raise ValueError(f'{onde} [{busca.site}] ("{busca.palavra_chave}"): {erro}') from None


def carregar(caminho: str | Path) -> Config:
    nome = Path(caminho).name
    with open(caminho, "rb") as f:
        try:
            dados = tomllib.load(f)
        except tomllib.TOMLDecodeError as erro:
            raise ValueError(f"{nome} tem um erro de escrita: {erro}") from None

    dados_limites = dados.get("limites", {})
    _checar_campos(dados_limites, Limites, f"{nome}, [limites]")
    limites = Limites(**dados_limites)
    for prefixo in ("pausa", "pausa_linkedin"):
        if getattr(limites, f"{prefixo}_min_s") > getattr(limites, f"{prefixo}_max_s"):
            raise ValueError(f"{nome}, [limites]: {prefixo}_min_s não pode ser maior que {prefixo}_max_s")
    for campo in ("max_requisicoes", "intervalo_minimo_min"):
        if getattr(limites, campo) < 0:
            raise ValueError(f"{nome}, [limites]: {campo} não pode ser negativo (use 0 para desligar)")

    buscas = []
    for i, dados_busca in enumerate(dados.get("buscas", []), start=1):
        onde = f"{nome}, busca {i}"
        _checar_campos(dados_busca, Busca, onde)
        busca = Busca(**dados_busca)
        _validar_site(busca, onde)  # falha cedo se o site ou algum filtro for inválido
        buscas.append(busca)

    if not buscas:
        raise ValueError(f"Nenhuma [[buscas]] ativa em {nome}")

    if "google_sheets" in dados:
        raise ValueError(
            f"{nome}: a seção [google_sheets] mudou para o arquivo {ARQUIVO_SHEETS} "
            "(veja o README, seção 'Google Sheets'). Apague-a do config.toml."
        )
    google_sheets = carregar_sheets(Path(caminho).with_name(ARQUIVO_SHEETS))
    filtro_sheets = carregar_filtro(Path(caminho).with_name(ARQUIVO_FILTRO))
    return Config(buscas=buscas, limites=limites, google_sheets=google_sheets, filtro_sheets=filtro_sheets)


def carregar_filtro(caminho: str | Path) -> FiltroSheets:
    """Lê filtro_sheets.toml. Sem o arquivo, ou com filtro_sql vazio, nada é filtrado."""
    caminho = Path(caminho)
    if not caminho.exists():
        return FiltroSheets()
    with open(caminho, "rb") as f:
        try:
            dados = tomllib.load(f)
        except tomllib.TOMLDecodeError as erro:
            raise ValueError(f"{caminho.name} tem um erro de escrita: {erro}") from None
    _checar_campos(dados, FiltroSheets, caminho.name)
    filtro = FiltroSheets(filtro_sql=str(dados.get("filtro_sql", "")).strip())
    if filtro.filtro_sql:
        _validar_filtro_sql(filtro.filtro_sql, caminho.name)
    return filtro


def _validar_filtro_sql(condicao: str, nome: str) -> None:
    """Falha cedo se a condição tiver ';' ou não for um SQL válido sobre a tabela vagas."""
    from .banco import Banco  # import aqui evita import circular e custo fora de uso

    if ";" in condicao:
        raise ValueError(f"{nome}: o filtro_sql não pode ter ';' (escreva só a condição do WHERE)")
    banco = Banco(":memory:")
    try:
        # EXPLAIN só compila a consulta: confere a sintaxe e os nomes de colunas sem ler dados
        banco.con.execute(f"EXPLAIN SELECT 1 FROM vagas WHERE ({condicao})")
    except sqlite3.Error as erro:
        raise ValueError(f"{nome}: filtro_sql inválido ({erro})") from None
    finally:
        banco.fechar()


def carregar_sheets(caminho: str | Path) -> GoogleSheets | None:
    """Lê google_sheets.toml. Sem o arquivo, o envio para o Google Sheets fica desligado."""
    caminho = Path(caminho)
    if not caminho.exists():
        return None
    with open(caminho, "rb") as f:
        try:
            dados = tomllib.load(f)
        except tomllib.TOMLDecodeError as erro:
            raise ValueError(f"{caminho.name} tem um erro de escrita: {erro}") from None
    _checar_campos(dados, GoogleSheets, caminho.name)
    conf = GoogleSheets(url_script=str(dados["url_script"]).strip(), senha=str(dados["senha"]))
    if not conf.url_script.startswith("https://script.google.com/") or not conf.url_script.endswith("/exec"):
        raise ValueError(
            f"{caminho.name}: url_script deve ser o 'URL do app da Web' do Apps Script "
            "(https://script.google.com/macros/s/.../exec)"
        )
    if not conf.senha.strip() or conf.senha == "troque-esta-senha":
        raise ValueError(f"{caminho.name}: escolha uma senha (a mesma do Apps Script)")
    return conf
