"""Transforma o HTML público do LinkedIn em dicionários.

Os seletores ficam aqui no topo: quando o LinkedIn mudar o layout, é só ajustar esta lista.
"""

from __future__ import annotations

import re
import unicodedata

from bs4 import BeautifulSoup, Tag

# --- Lista de vagas ---
SEL_CARD = ["[data-entity-urn*='jobPosting']", ".job-search-card", ".base-search-card"]
SEL_TITULO = [".base-search-card__title", "h3"]
SEL_EMPRESA = [".base-search-card__subtitle", "h4"]
SEL_LOCAL = [".job-search-card__location"]
SEL_LINK = ["a.base-card__full-link", "a[href*='/jobs/view/']"]

# --- Página de detalhe ---
SEL_DESCRICAO = [".show-more-less-html__markup", ".description__text"]
SEL_CRITERIO = ["li.description__job-criteria-item"]
SEL_CRITERIO_TITULO = [".description__job-criteria-subheader", "h3"]
SEL_CRITERIO_VALOR = [".description__job-criteria-text", "span"]
SEL_CANDIDATOS = [".num-applicants__caption"]

RE_ID_URN = re.compile(r"jobPosting:(\d+)")
RE_ID_LINK = re.compile(r"/jobs/view/(?:[^/?]*-)?(\d{6,})")


def _primeiro(raiz: Tag, seletores: list[str]) -> Tag | None:
    for seletor in seletores:
        achado = raiz.select_one(seletor)
        if achado is not None:
            return achado
    return None


def _texto(raiz: Tag, seletores: list[str]) -> str | None:
    el = _primeiro(raiz, seletores)
    if el is None:
        return None
    texto = " ".join(el.get_text(" ", strip=True).split())
    return texto or None


def _normalizar(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


def _job_id(card: Tag) -> str | None:
    for el in [card, *card.select("[data-entity-urn]")]:
        achado = RE_ID_URN.search(el.get("data-entity-urn", ""))
        if achado:
            return achado.group(1)
    link = _primeiro(card, SEL_LINK)
    if link is not None:
        achado = RE_ID_LINK.search(link.get("href", ""))
        if achado:
            return achado.group(1)
    return None


def parse_lista(html: str) -> list[dict]:
    """Extrai os cards de uma página da lista. Retorna [] se não houver vagas."""
    soup = BeautifulSoup(html, "lxml")
    # todos os seletores de uma vez, em ordem no documento; o elemento externo de cada
    # card vem primeiro e o filtro por job_id descarta os internos repetidos
    cards = soup.select(", ".join(SEL_CARD))

    vagas: list[dict] = []
    vistos: set[str] = set()
    for card in cards:
        job_id = _job_id(card)
        if not job_id or job_id in vistos:
            continue
        vistos.add(job_id)
        data = card.select_one("time[datetime]")
        vagas.append(
            {
                "job_id": job_id,
                "titulo": _texto(card, SEL_TITULO),
                "empresa": _texto(card, SEL_EMPRESA),
                "local": _texto(card, SEL_LOCAL),
                "publicada_em": data["datetime"] if data else None,
            }
        )
    return vagas


# títulos dos critérios (em pt e en) -> nome da coluna
CRITERIOS = {
    "nivel": "nivel",
    "seniority": "nivel",
    "tipo de emprego": "tipo_contrato",
    "employment": "tipo_contrato",
    "funcao": "area",
    "function": "area",
}


def _texto_limpo(el: Tag) -> str | None:
    for br in el.find_all("br"):
        br.replace_with("\n")
    linhas = (" ".join(l.split()) for l in el.get_text("\n").splitlines())
    texto = "\n".join(l for l in linhas if l)
    return texto or None


def html_para_texto(html: str | None) -> str | None:
    """Converte um trecho de HTML em texto, uma linha por bloco, sem linhas vazias."""
    if not html:
        return None
    return _texto_limpo(BeautifulSoup(html, "lxml"))


def _descricao(raiz: Tag) -> str | None:
    el = _primeiro(raiz, SEL_DESCRICAO)
    return _texto_limpo(el) if el is not None else None


def parse_detalhe(html: str) -> dict:
    """Extrai descrição, nível, tipo de contrato, área e nº de candidatos da página da vaga."""
    soup = BeautifulSoup(html, "lxml")
    detalhe: dict = {
        "descricao": _descricao(soup),
        "nivel": None,
        "tipo_contrato": None,
        "area": None,
        "candidatos": _texto(soup, SEL_CANDIDATOS),
    }
    for item in soup.select(", ".join(SEL_CRITERIO)):
        titulo = _texto(item, SEL_CRITERIO_TITULO) or ""
        valor = _texto(item, SEL_CRITERIO_VALOR)
        for chave, coluna in CRITERIOS.items():
            if chave in _normalizar(titulo):
                detalhe[coluna] = valor
                break
    return detalhe
