from urllib.parse import parse_qs, urlparse

import pytest

from wb_trampo.config import Busca
from wb_trampo.urls import parametros, url_lista, url_vaga


def test_traduz_filtros_legiveis_com_e_sem_acento():
    busca = Busca("python", "Brasil", modalidade=["Remoto", "híbrido"],
                  nivel=["júnior", "pleno", "senior"], publicada="semana")
    assert parametros(busca) == {
        "keywords": "python",
        "location": "Brasil",
        "f_TPR": "r604800",
        "f_E": "2,4",  # pleno e sênior são o mesmo código, sem repetir
        "f_WT": "2,3",
    }


def test_filtros_opcionais_ficam_de_fora():
    assert parametros(Busca("dados")) == {"keywords": "dados"}


def test_valor_invalido_explica_opcoes():
    with pytest.raises(ValueError, match="modalidade desconhecido.*remoto"):
        parametros(Busca("x", modalidade=["home office"]))


def test_url_lista_tem_paginacao():
    url = url_lista(Busca("python", "São Paulo"), start=20)
    qs = parse_qs(urlparse(url).query)
    assert qs["start"] == ["20"]
    assert qs["location"] == ["São Paulo"]


@pytest.mark.parametrize(
    "publicada, esperado",
    [(3600, "r3600"), ("7200", "r7200"), (86400, "r86400"),
     ("24h", "r86400"), ("semana", "r604800"), ("mês", "r2592000")],
)
def test_publicada_em_segundos_ou_atalho(publicada, esperado):
    assert parametros(Busca("x", publicada=publicada))["f_TPR"] == esperado


@pytest.mark.parametrize("publicada", [0, -5, True, 1.5, "ontem", "1 hora"])
def test_publicada_invalida(publicada):
    with pytest.raises(ValueError, match="publicada inválida"):
        parametros(Busca("x", publicada=publicada))


def test_url_vaga_limpa():
    assert url_vaga("4012345678") == "https://www.linkedin.com/jobs/view/4012345678/"
