"""Monta as URLs públicas de vagas do LinkedIn a partir dos filtros legíveis."""

from __future__ import annotations

import unicodedata
from typing import TYPE_CHECKING
from urllib.parse import urlencode

if TYPE_CHECKING:
    from .config import Busca

BASE_LISTA = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
BASE_DETALHE = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{job_id}"
BASE_VAGA = "https://www.linkedin.com/jobs/view/{job_id}/"

PUBLICADA = {"24h": "r86400", "dia": "r86400", "semana": "r604800", "mes": "r2592000"}
NIVEL = {
    "estagio": "1",
    "junior": "2",
    "associado": "3",
    "pleno": "4",
    "senior": "4",
    "pleno-senior": "4",
    "diretor": "5",
    "executivo": "6",
}
MODALIDADE = {"presencial": "1", "remoto": "2", "hibrido": "3"}


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sem_acento.strip().lower()


def _traduzir(valores: list[str], tabela: dict[str, str], nome: str) -> str:
    codigos: list[str] = []
    for valor in valores:
        chave = _normalizar(valor)
        if chave not in tabela:
            opcoes = ", ".join(sorted(tabela))
            raise ValueError(f"{nome} desconhecido: {valor!r}. Use um de: {opcoes}")
        codigo = tabela[chave]
        if codigo not in codigos:
            codigos.append(codigo)
    return ",".join(codigos)


def segundos(publicada: str | int) -> int:
    """Converte segundos (3600 ou "3600") ou um atalho (24h/semana/mes) em segundos."""
    valor = None
    if isinstance(publicada, bool):  # True/False também são int em Python
        valor = None
    elif isinstance(publicada, int):
        valor = publicada
    elif isinstance(publicada, str) and publicada.strip().isdigit():
        valor = int(publicada.strip())
    elif isinstance(publicada, str) and _normalizar(publicada) in PUBLICADA:
        valor = int(PUBLICADA[_normalizar(publicada)].lstrip("r"))

    if valor is None or valor <= 0:
        raise ValueError(
            f"publicada inválida: {publicada!r}. "
            "Use segundos (ex.: 3600 = 1 hora, 86400 = 1 dia) ou 24h/semana/mes"
        )
    return valor


def _tempo(publicada: str | int) -> str:
    """Valor do filtro f_TPR do LinkedIn (ex.: r86400)."""
    return f"r{segundos(publicada)}"


def parametros(busca: Busca) -> dict[str, str]:
    """Traduz uma Busca para os parâmetros de filtro do LinkedIn (valida os valores)."""
    params = {"keywords": busca.palavra_chave}
    if busca.local:
        params["location"] = busca.local
    if busca.publicada is not None and busca.publicada != "":
        params["f_TPR"] = _tempo(busca.publicada)
    if busca.nivel:
        params["f_E"] = _traduzir(busca.nivel, NIVEL, "nivel")
    if busca.modalidade:
        params["f_WT"] = _traduzir(busca.modalidade, MODALIDADE, "modalidade")
    return params


def url_lista(busca: Busca, start: int = 0) -> str:
    return f"{BASE_LISTA}?{urlencode({**parametros(busca), 'start': start})}"


def url_detalhe(job_id: str) -> str:
    return BASE_DETALHE.format(job_id=job_id)


def url_vaga(job_id: str) -> str:
    """Link limpo da vaga (sem parâmetros de rastreio), usado no banco e no Excel."""
    return BASE_VAGA.format(job_id=job_id)
