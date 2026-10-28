"""O arquivo de log deve mostrar até onde o robô foi e onde falhou."""

import logging

import pytest

from wb_trampo import __main__ as cli
from wb_trampo.cliente import Bloqueado


@pytest.fixture
def pasta(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(
        '[limites]\nmax_vagas_por_busca = 5\n\n[[buscas]]\nsite = "linkedin"\npalavra_chave = "python"\n',
        encoding="utf-8",
    )
    yield tmp_path
    for h in list(logging.getLogger("wb_trampo").handlers):  # libera o arquivo no Windows
        h.close()


def _ler_log(pasta):
    (arquivo,) = (pasta / "data" / "logs").glob("wb_trampo_*.log")
    return arquivo.read_text(encoding="utf-8")


def test_bloqueio_fica_registrado(pasta, monkeypatch, html_lista):
    respostas = iter([html_lista])

    def get_falso(self, url):
        try:
            return next(respostas)
        except StopIteration:
            raise Bloqueado("HTTP 429 de teste") from None

    monkeypatch.setattr(cli.Cliente, "get", get_falso)
    codigo = cli.main(["buscar", "--sem-descricao"])

    texto = _ler_log(pasta)
    assert codigo == 2
    assert "Busca 1/1 [linkedin]: 'python'" in texto
    assert "Página 1" in texto and "Página 2" in texto     # até onde foi
    assert "Desenvolvedor Python Júnior" in texto
    assert "Falhou na busca 1/1 [linkedin]" in texto                  # onde falhou
    assert "HTTP 429 de teste" in texto
    assert "Planilha salva" in texto                       # mesmo assim gerou o Excel


def test_erro_inesperado_grava_traceback(pasta, monkeypatch):
    def quebra(self, url):
        raise RuntimeError("bug de teste")

    monkeypatch.setattr(cli.Cliente, "get", quebra)
    codigo = cli.main(["buscar", "--sem-excel"])

    texto = _ler_log(pasta)
    assert codigo == 1
    assert "Traceback" in texto and "RuntimeError: bug de teste" in texto
    assert "fim (código de saída 1)" in texto
