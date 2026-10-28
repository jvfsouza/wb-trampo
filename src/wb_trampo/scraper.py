"""Orquestra a coleta: para cada busca, pede as vagas ao site certo, busca detalhes e grava no banco."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

from .banco import Banco
from .cliente import HOST_LINKEDIN, Cliente, LimiteRequisicoes
from .config import Busca, Config
from .fontes import FONTES

log = logging.getLogger(__name__)


@dataclass
class Resumo:
    vistas: int = 0
    novas: int = 0
    interrompida: bool = False  # parou no teto de requisições


def _estimar_linkedin(limite: int, buscar_descricao: bool, cliente: Cliente) -> None:
    """Mostra quanto tempo a busca do LinkedIn pode levar com a pausa configurada."""
    pausa = getattr(cliente, "pausa", None)
    if pausa is None:
        return
    minimo, maximo = pausa(HOST_LINKEDIN)
    requisicoes = math.ceil(limite / 10) + (limite if buscar_descricao else 0)
    minutos = requisicoes * (minimo + maximo) / 2 / 60
    log.info("  LinkedIn: pausa de %g–%g s entre requisições; até ~%d requisições ≈ %.0f min.",
             minimo, maximo, requisicoes, minutos)


def coletar_busca(
    busca: Busca,
    config: Config,
    banco: Banco,
    cliente: Cliente,
    execucao: int,
    buscar_descricao: bool,
) -> Resumo:
    fonte = FONTES[busca.site]
    resumo = Resumo()
    limite = config.limites.max_vagas_por_busca
    if busca.site == "linkedin":
        _estimar_linkedin(limite, buscar_descricao, cliente)
    for card in fonte.listar(busca, cliente, limite):
        resumo.vistas += 1
        job_id = card["job_id"]
        if banco.existe(job_id):
            banco.marcar_visto(job_id)
            log.info("  = [%d/%d] já vista: %s | %s", resumo.vistas, limite, card.get("titulo"), card.get("empresa"))
            continue

        detalhe = fonte.detalhar(card, cliente) if buscar_descricao else {}
        vaga = {
            **card,
            **{k: v for k, v in detalhe.items() if v is not None},
            "site": busca.site,
            "busca": busca.palavra_chave,
        }
        banco.salvar(vaga, execucao)
        resumo.novas += 1
        log.info("  + [%d/%d] NOVA: %s | %s", resumo.vistas, limite, vaga.get("titulo"), vaga.get("empresa"))
    return resumo


def executar(
    config: Config,
    banco: Banco,
    cliente: Cliente,
    buscar_descricao: bool | None = None,
) -> Resumo:
    """Roda todas as buscas. Se algo falhar (ex.: Bloqueado), a exceção sobe,
    mas o que já foi coletado continua salvo no banco."""
    if buscar_descricao is None:
        buscar_descricao = config.limites.buscar_descricao
    total = Resumo()
    execucao = banco.iniciar_execucao()
    log.info("Execução #%d iniciada (%d buscas, descrição: %s)",
             execucao, len(config.buscas), "sim" if buscar_descricao else "não")
    try:
        for i, busca in enumerate(config.buscas, start=1):
            log.info("Busca %d/%d [%s]: '%s' em '%s'", i, len(config.buscas), busca.site,
                     busca.palavra_chave, busca.local or "qualquer lugar")
            try:
                r = coletar_busca(busca, config, banco, cliente, execucao, buscar_descricao)
            except LimiteRequisicoes:
                log.warning(
                    "Teto de %d requisições atingido na busca %d/%d; o que foi coletado está salvo "
                    "e as buscas restantes ficam para a próxima execução (aumente max_requisicoes "
                    "no config.toml se quiser).", config.limites.max_requisicoes, i, len(config.buscas),
                )
                total.interrompida = True
                # as vagas novas da busca interrompida também já estão no banco
                total.novas = banco.con.execute(
                    "SELECT COUNT(*) FROM vagas WHERE execucao = ?", (execucao,)
                ).fetchone()[0]
                break
            except Exception:
                log.error("Falhou na busca %d/%d [%s] ('%s') depois de %d vagas novas no total.",
                          i, len(config.buscas), busca.site, busca.palavra_chave, total.novas)
                raise
            log.info("Busca %d/%d concluída: %d vagas encontradas, %d novas.",
                     i, len(config.buscas), r.vistas, r.novas)
            total.vistas += r.vistas
            total.novas += r.novas
    finally:
        banco.finalizar_execucao(execucao)
        if hasattr(cliente, "resumo"):
            log.info("Requisições nesta execução: %s", cliente.resumo())
    return total
