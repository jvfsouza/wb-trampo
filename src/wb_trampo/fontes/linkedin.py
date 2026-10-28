"""LinkedIn: páginas públicas de vagas (sem login). Os filtros são aplicados pelo próprio site."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from ..cliente import NaoEncontrado
from ..parser import parse_detalhe, parse_lista
from ..urls import parametros, url_detalhe, url_lista

if TYPE_CHECKING:
    from ..cliente import Cliente
    from ..config import Busca

log = logging.getLogger(__name__)

PASTA_DEBUG = Path("data/debug")


def _salvar_debug(html: str, nome: str) -> None:
    PASTA_DEBUG.mkdir(parents=True, exist_ok=True)
    caminho = PASTA_DEBUG / f"{nome}_{datetime.now():%Y%m%d_%H%M%S}.html"
    caminho.write_text(html, encoding="utf-8")
    log.warning(
        "Nenhuma vaga reconhecida no HTML (%d caracteres); cópia salva em %s para ajustar os seletores.",
        len(html), caminho,
    )


class LinkedIn:
    nome = "linkedin"

    def validar(self, busca: Busca) -> None:
        parametros(busca)

    def listar(self, busca: Busca, cliente: Cliente, limite: int) -> Iterator[dict]:
        log.debug("Filtros: %s", parametros(busca))
        entregues = 0
        start = 0
        pagina = 1
        while entregues < limite:
            log.info("  Página %d (vagas %d em diante)...", pagina, start + 1)
            html = cliente.get(url_lista(busca, start))
            cards = parse_lista(html)
            log.debug("  %d cards reconhecidos na página %d", len(cards), pagina)
            if not cards:
                # página vazia é o fim normal; HTML grande sem cards indica mudança de layout
                if start == 0 and len(html.strip()) > 500:
                    _salvar_debug(html, "lista")
                else:
                    log.info("  Fim dos resultados.")
                return

            for card in cards:
                if entregues >= limite:
                    break
                entregues += 1
                # no LinkedIn a modalidade é só o filtro pedido (o card não informa)
                yield {**card, "modalidade": ", ".join(busca.modalidade) or None}

            start += len(cards)
            pagina += 1
        log.info("  Limite de %d vagas por busca atingido.", limite)

    def detalhar(self, vaga: dict, cliente: Cliente) -> dict:
        job_id = vaga["job_id"]
        try:
            detalhe = parse_detalhe(cliente.get(url_detalhe(job_id)))
        except NaoEncontrado:
            log.warning("  Vaga %s não existe mais (404); salvando sem detalhes.", job_id)
            return {}
        if not detalhe.get("descricao"):
            log.warning("  Descrição não encontrada para a vaga %s", job_id)
        return detalhe
