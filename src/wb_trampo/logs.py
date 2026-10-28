"""Configuração dos logs: tela + arquivo diário em data/logs/.

A tela mostra o progresso (INFO). O arquivo guarda tudo, inclusive cada requisição (DEBUG)
e o traceback completo dos erros, para descobrir onde o robô parou.
"""

from __future__ import annotations

import logging
import sys
from datetime import date
from pathlib import Path

NOME = "wb_trampo"


def configurar(pasta: str | Path = "data/logs", verbose: bool = False) -> Path:
    """Liga os logs e retorna o caminho do arquivo do dia."""
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / f"{NOME}_{date.today():%Y-%m-%d}.log"

    logger = logging.getLogger(NOME)
    logger.setLevel(logging.DEBUG)
    for handler in list(logger.handlers):  # evita duplicar se chamado de novo
        logger.removeHandler(handler)
        handler.close()

    no_arquivo = logging.FileHandler(arquivo, encoding="utf-8")
    no_arquivo.setLevel(logging.DEBUG)
    no_arquivo.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-7s [%(name)s] %(message)s")
    )

    na_tela = logging.StreamHandler(sys.stdout)
    na_tela.setLevel(logging.DEBUG if verbose else logging.INFO)
    na_tela.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S"))

    logger.addHandler(no_arquivo)
    logger.addHandler(na_tela)
    return arquivo
