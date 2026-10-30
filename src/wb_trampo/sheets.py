"""Envia as vagas novas da última execução para uma aba do dia na planilha Google.

O envio é feito para um Apps Script instalado na própria planilha (`apps_script/Codigo.gs`),
publicado como "App da Web". O robô manda as linhas com uma senha; o script cria a aba do dia
e acrescenta as vagas cujo link ainda não está lá. Não precisa de Google Cloud nem de login.
"""

from __future__ import annotations

import json
import logging
import unicodedata
from collections.abc import Callable
from datetime import date, datetime

import requests

from .banco import Banco
from .config import GoogleSheets

log = logging.getLogger(__name__)

# coluna do banco -> título na planilha (na ordem em que aparecem)
COLUNAS = {
    "titulo": "Título",
    "empresa": "Empresa",
    "site": "Site",
    "local": "Local",
    "modalidade": "Modalidade",
    "tipo_contrato": "Contrato",
    "url": "Link",
    # a descrição não vai para o Sheets (fica no banco e no Excel)
    "publicada_em": "Publicada em",  # Gupy: dia e hora; LinkedIn: só o dia
}
COLUNA_SITE = list(COLUNAS).index("site")
COLUNA_LINK = list(COLUNAS).index("url")
COLUNAS_TEXTO = (list(COLUNAS).index("titulo"), list(COLUNAS).index("empresa"))  # ordem alfabética
NOME_SITE = {"linkedin": "LinkedIn", "gupy": "Gupy"}
LIMITE_CELULA = 45_000  # o Google Sheets aceita no máximo 50.000 caracteres por célula
COMO_CONFIGURAR = "Veja no README a seção 'Google Sheets'."


class ErroSheets(Exception):
    """Não foi possível enviar para o Google Sheets (com a explicação do que fazer)."""


def _celula(valor) -> str:
    texto = "" if valor is None else str(valor)
    if len(texto) > LIMITE_CELULA:
        texto = texto[:LIMITE_CELULA] + "…"
    # texto começando com = + - @ viraria fórmula no Sheets; o apóstrofo força texto
    if texto[:1] in ("=", "+", "-", "@"):
        texto = "'" + texto
    return texto


def _chave_ordem(valores) -> tuple[str, str]:
    """Título e empresa sem acento e sem maiúsculas (ex.: 'Última' fica entre 'Ultimo' e 'Vaga')."""

    def normalizar(texto) -> str:
        texto = "" if texto is None else str(texto)
        texto = unicodedata.normalize("NFKD", texto)
        return "".join(c for c in texto if not unicodedata.combining(c)).casefold()

    return normalizar(valores[COLUNAS_TEXTO[0]]), normalizar(valores[COLUNAS_TEXTO[1]])


def vagas_novas(banco: Banco, execucao: int | None = None, filtro_sql: str = "") -> list[list[str]]:
    """Linhas (na ordem de COLUNAS) das vagas que apareceram pela 1ª vez na execução, em ordem
    alfabética de título (depois empresa). `filtro_sql` é uma condição do WHERE (vinda do
    filtro_sheets.toml); vazio = sem filtro."""
    if execucao is None:
        execucao = banco.ultima_execucao()
    if execucao is None:
        return []
    extra = f" AND ({filtro_sql})" if filtro_sql else ""
    cur = banco.con.execute(
        f"SELECT {', '.join(COLUNAS)} FROM vagas WHERE execucao = ?{extra} ORDER BY rowid", (execucao,)
    )
    # sorted é estável: vagas com o mesmo título e empresa mantêm a ordem de chegada
    ordenadas = sorted(cur, key=_chave_ordem)
    return [[_celula(v) for v in valores] for valores in ordenadas]


def separar_por_filtro(
    banco: Banco, filtro_sql: str, execucao: int | None = None
) -> tuple[list[list[str]], list[list[str]]]:
    """Devolve (passaram, filtradas) entre as vagas novas da execução. A separação é feita em
    Python, pelo link: com título NULL, `NOT (filtro)` no SQL deixaria a vaga de fora das duas listas."""
    todas = vagas_novas(banco, execucao)
    passaram = vagas_novas(banco, execucao, filtro_sql=filtro_sql)
    links_que_passaram = {linha[COLUNA_LINK] for linha in passaram}
    filtradas = [linha for linha in todas if linha[COLUNA_LINK] not in links_que_passaram]
    return passaram, filtradas


def _postar(url: str, corpo: dict) -> dict:
    """POST para o Apps Script e devolve a resposta JSON dele."""
    try:
        # o Apps Script responde com um redirecionamento; o requests segue sozinho
        resp = requests.post(url, data=json.dumps(corpo), timeout=60,
                             headers={"Content-Type": "application/json"})
    except requests.RequestException as erro:
        raise ErroSheets(f"não consegui falar com o Apps Script ({erro})") from erro
    if resp.status_code == 404:
        raise ErroSheets(f"link do Apps Script não encontrado (HTTP 404). Confira o url_script. {COMO_CONFIGURAR}")
    if resp.status_code != 200:
        raise ErroSheets(f"o Apps Script respondeu HTTP {resp.status_code}")
    try:
        return resp.json()
    except ValueError:
        # normalmente é a página de login do Google: a implantação não está como "Qualquer pessoa"
        raise ErroSheets(
            "o Apps Script não respondeu com JSON. Confira se a implantação está com "
            "'Executar como: Eu' e 'Quem pode acessar: Qualquer pessoa', e se o url_script "
            f"termina em /exec. {COMO_CONFIGURAR}"
        ) from None


def dia_da_execucao(banco: Banco, execucao: int | None = None) -> date | None:
    """Dia em que a execução (por padrão, a última) foi feita."""
    if execucao is None:
        execucao = banco.ultima_execucao()
    linha = banco.con.execute("SELECT iniciada_em FROM execucoes WHERE id = ?", (execucao,)).fetchone()
    return datetime.fromisoformat(linha[0]).date() if linha else None


def nome_aba(dia: date, site: str) -> str:
    """Ex.: '2026-10-27 Gupy'."""
    return f"{dia.isoformat()} {NOME_SITE.get(site, site.capitalize())}"


def enviar_novas(
    banco: Banco,
    conf: GoogleSheets,
    postar: Callable[[str, dict], dict] = _postar,
    hoje: date | None = None,
    filtro_sql: str = "",
) -> int:
    """Manda as vagas novas da última execução para abas separadas por site, com o dia da busca
    no nome (ex.: '2026-10-27 Gupy'). O script não repete links. Devolve quantas entraram.
    Só vão as vagas que passam em `filtro_sql` (ver filtro_sheets.toml)."""
    linhas = vagas_novas(banco, filtro_sql=filtro_sql)
    if filtro_sql:
        total_novas = len(vagas_novas(banco))
        log.info("Google Sheets: %d vagas novas, %d passaram no filtro.", total_novas, len(linhas))
    if not linhas:
        log.info("Google Sheets: nenhuma vaga nova para enviar.")
        return 0
    dia = hoje or dia_da_execucao(banco) or date.today()

    por_site: dict[str, list[list[str]]] = {}
    for linha in linhas:
        por_site.setdefault(linha[COLUNA_SITE], []).append(linha)

    total = 0
    for site, linhas_site in por_site.items():
        aba = nome_aba(dia, site)
        log.info("Google Sheets: enviando %d vagas novas para a aba %s...", len(linhas_site), aba)
        resposta = postar(conf.url_script, {
            "senha": conf.senha,
            "aba": aba,
            "cabecalho": list(COLUNAS.values()),
            "linhas": linhas_site,
        })
        if not resposta.get("ok"):
            raise ErroSheets(f"o Apps Script recusou o envio: {resposta.get('erro') or resposta}")
        if resposta.get("criada"):
            log.info("Google Sheets: aba %s criada.", aba)
        adicionadas = int(resposta.get("adicionadas", 0))
        repetidas = int(resposta.get("repetidas", 0))
        log.info(
            "Google Sheets: %d vagas adicionadas na aba %s%s.",
            adicionadas, aba, f" ({repetidas} já estavam lá)" if repetidas else "",
        )
        total += adicionadas
    return total
