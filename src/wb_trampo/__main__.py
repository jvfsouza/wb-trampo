"""Linha de comando: `python -m wb_trampo buscar | exportar | enviar-sheets`."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from . import config as cfg
from . import logs
from .banco import Banco
from .cliente import HOST_LINKEDIN, Bloqueado, Cliente
from .exportar import exportar
from .scraper import executar
from .sheets import COLUNA_LINK, ErroSheets, enviar_novas, separar_por_filtro

log = logging.getLogger("wb_trampo")


def _ler_config(caminho: str) -> cfg.Config | None:
    log.info("Lendo configuração de %s", caminho)
    try:
        return cfg.carregar(caminho)
    except FileNotFoundError:
        log.error("Arquivo de configuração não encontrado: %s", caminho)
    except ValueError as erro:
        log.error("Problema no arquivo de configuração: %s", erro)
    return None


def _enviar_sheets(banco: Banco, config: cfg.Config) -> int:
    """Envia as vagas novas para o Google Sheets. Devolve 0 se deu certo (ou está desligado)."""
    if config.google_sheets is None:
        return 0
    try:
        enviar_novas(banco, config.google_sheets, filtro_sql=config.filtro_sheets.filtro_sql)
        return 0
    except ErroSheets as erro:
        log.error("Google Sheets: %s", erro)
    except Exception:
        log.exception("Google Sheets: falha ao enviar as vagas.")
    log.info("Banco e Excel estão salvos. Para tentar de novo: python -m wb_trampo enviar-sheets")
    return 1


def _cedo_demais(banco: Banco, intervalo_min: float) -> bool:
    """True (e explica) se a última execução começou há menos de `intervalo_min` minutos."""
    inicio = banco.inicio_ultima_execucao()
    if not intervalo_min or inicio is None:
        return False
    passados = (datetime.now() - inicio).total_seconds() / 60
    if passados >= intervalo_min:
        return False
    log.warning(
        "A última busca foi há %.0f min; para poupar o seu IP, espere mais %.0f min "
        "(intervalo_minimo_min = %g no config.toml) ou rode com --forcar.",
        passados, intervalo_min - passados, intervalo_min,
    )
    return True


def cmd_buscar(args: argparse.Namespace) -> int:
    config = _ler_config(args.config)
    if config is None:
        return 1
    banco = Banco(args.banco)
    log.info("Banco: %s (%d vagas já salvas)", args.banco, banco.contar())
    if not args.forcar and _cedo_demais(banco, config.limites.intervalo_minimo_min):
        banco.fechar()
        return 0
    lim = config.limites
    cliente = Cliente(
        lim.pausa_min_s, lim.pausa_max_s,
        pausas_por_host={HOST_LINKEDIN: (lim.pausa_linkedin_min_s, lim.pausa_linkedin_max_s)},
        max_requisicoes=lim.max_requisicoes,
    )
    codigo = 0
    try:
        # None = usa o valor do config.toml
        resumo = executar(config, banco, cliente, buscar_descricao=False if args.sem_descricao else None)
        log.info("Pronto: %d vagas vistas, %d novas. Total no banco: %d.",
                 resumo.vistas, resumo.novas, banco.contar())
    except Bloqueado as erro:
        log.error("Parado: %s", erro)
        log.info("O que já foi coletado ficou salvo (%d vagas no banco).", banco.contar())
        codigo = 2
    except KeyboardInterrupt:
        log.warning("Interrompido pelo usuário. O que já foi coletado ficou salvo (%d vagas no banco).",
                    banco.contar())
        codigo = 130
    except Exception:
        log.exception("Erro inesperado. O que já foi coletado ficou salvo (%d vagas no banco).",
                      banco.contar())
        codigo = 1

    if not args.sem_excel:
        try:
            exportar(banco, args.excel)
        except Exception:
            log.exception("Falha ao gerar a planilha.")
            codigo = codigo or 1
    if not args.sem_sheets and codigo != 130:
        falha_sheets = _enviar_sheets(banco, config)  # roda mesmo se a busca foi bloqueada
        codigo = codigo or falha_sheets
    banco.fechar()
    return codigo


def cmd_exportar(args: argparse.Namespace) -> int:
    banco = Banco(args.banco)
    try:
        exportar(banco, args.saida, filtro=args.filtro)
    finally:
        banco.fechar()
    return 0


def _simular_filtro(args: argparse.Namespace) -> int:
    """Mostra quais vagas novas passariam no filtro_sheets.toml e quais seriam barradas.
    Não envia nada e não lê o google_sheets.toml."""
    try:
        filtro = cfg.carregar_filtro(Path(args.config).with_name(cfg.ARQUIVO_FILTRO))
    except ValueError as erro:
        log.error("Problema no filtro: %s", erro)
        return 1
    banco = Banco(args.banco)
    try:
        passaram, filtradas = separar_por_filtro(banco, filtro.filtro_sql)
    finally:
        banco.fechar()
    if not filtro.filtro_sql:
        print("Sem filtro (filtro_sheets.toml ausente ou com filtro_sql vazio): todas iriam para o Sheets.")
    print(f"Vagas novas da última execução: {len(passaram) + len(filtradas)}. "
          f"Passam: {len(passaram)}. Filtradas: {len(filtradas)}.")
    for secao, linhas in (("PASSARAM", passaram), ("FILTRADAS", filtradas)):
        print(f"\n== {secao} ==")
        for linha in linhas:
            print(f"{linha[0]} | {linha[1]} | {linha[COLUNA_LINK]}")
    return 0


def cmd_enviar_sheets(args: argparse.Namespace) -> int:
    if args.simular:
        return _simular_filtro(args)
    config = _ler_config(args.config)
    if config is None:
        return 1
    if config.google_sheets is None:
        log.error("O envio para o Google Sheets não está configurado: crie o arquivo google_sheets.toml "
                  "(veja o README, seção 'Google Sheets').")
        return 1
    banco = Banco(args.banco)
    try:
        return _enviar_sheets(banco, config)
    finally:
        banco.fechar()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wb_trampo", description="Busca vagas públicas no LinkedIn e na Gupy.")
    parser.add_argument("--banco", default="data/vagas.db", help="arquivo SQLite (padrão: data/vagas.db)")
    parser.add_argument("--logs", default="data/logs", help="pasta dos arquivos de log (padrão: data/logs)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="mostra na tela cada requisição (o arquivo de log sempre tem tudo)")
    sub = parser.add_subparsers(dest="comando", required=True)

    p_buscar = sub.add_parser("buscar", help="roda as buscas do config e atualiza banco e Excel")
    p_buscar.add_argument("--config", default="config.toml")
    p_buscar.add_argument("--sem-descricao", action="store_true", help="não abre cada vaga (mais rápido)")
    p_buscar.add_argument("--sem-excel", action="store_true", help="não gera a planilha no final")
    p_buscar.add_argument("--excel", default="data/vagas.xlsx", help="onde salvar a planilha")
    p_buscar.add_argument("--sem-sheets", action="store_true", help="não envia para o Google Sheets")
    p_buscar.add_argument("--forcar", action="store_true",
                          help="busca mesmo se a última execução foi há pouco (ignora intervalo_minimo_min)")
    p_buscar.set_defaults(func=cmd_buscar)

    p_exp = sub.add_parser("exportar", help="gera a planilha a partir do banco")
    p_exp.add_argument("--filtro", help="só vagas com este texto no título ou descrição")
    p_exp.add_argument("--saida", default="data/vagas.xlsx")
    p_exp.set_defaults(func=cmd_exportar)

    p_sh = sub.add_parser("enviar-sheets",
                          help="envia (de novo) as vagas novas da última execução para o Google Sheets")
    p_sh.add_argument("--config", default="config.toml")
    p_sh.add_argument("--simular", action="store_true",
                      help="mostra quais vagas passam no filtro_sheets.toml e quais seriam barradas (não envia)")
    p_sh.set_defaults(func=cmd_enviar_sheets)

    args = parser.parse_args(argv)
    arquivo_log = logs.configurar(args.logs, args.verbose)
    log.info("===== wb_trampo %s | log em %s =====", args.comando, arquivo_log)
    try:
        codigo = args.func(args)
    except Exception:
        log.exception("Erro inesperado em '%s'.", args.comando)
        codigo = 1
    log.info("===== fim (código de saída %d) =====", codigo)
    return codigo


if __name__ == "__main__":
    sys.exit(main())
