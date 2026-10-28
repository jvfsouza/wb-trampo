import copy
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from wb_trampo.config import Busca
from wb_trampo.fontes.gupy import Gupy

RESPOSTA = json.loads((Path(__file__).parent / "fixtures" / "gupy" / "jobs.json").read_text(encoding="utf-8"))


class ClienteFalso:
    """Devolve as vagas do fixture em páginas de `por_pagina`, como a API faria."""

    def __init__(self, resposta=RESPOSTA, por_pagina=50):
        self.itens = resposta["data"]
        self.por_pagina = por_pagina
        self.urls = []

    def get_json(self, url):
        self.urls.append(url)
        offset = int(parse_qs(urlparse(url).query)["offset"][0])
        pagina = self.itens[offset:offset + self.por_pagina]
        return {"data": pagina, "pagination": {"limit": self.por_pagina, "offset": offset,
                                               "total": len(self.itens)}}


def _busca(**kw):
    return Busca(kw.pop("palavra_chave", "backend"), site="gupy", **kw)


def _listar(busca, cliente=None, limite=100):
    return list(Gupy().listar(busca, cliente or ClienteFalso(), limite))


def _qs(url):
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


# --- URL -------------------------------------------------------------------

def test_url_basica():
    assert _qs(Gupy().url(_busca(), offset=50)) == {"jobName": "backend", "limit": "50", "offset": "50"}


@pytest.mark.parametrize("local", ["sao paulo", "São Paulo", "SP", "sp"])
def test_estado_vai_para_a_api(local):
    qs = _qs(Gupy().url(_busca(local=local)))
    assert qs["state"] == "São Paulo"
    assert "city" not in qs


def test_cidade_vai_para_a_api():
    qs = _qs(Gupy().url(_busca(local=" São José dos Campos ")))
    assert qs["city"] == "São José dos Campos"
    assert "state" not in qs


def test_uma_modalidade_vai_para_a_api_varias_nao():
    assert _qs(Gupy().url(_busca(modalidade=["remoto"])))["workplaceType"] == "remote"
    assert _qs(Gupy().url(_busca(modalidade=["híbrido"])))["workplaceType"] == "hybrid"
    assert "workplaceType" not in _qs(Gupy().url(_busca(modalidade=["remoto", "hibrido"])))


def test_nivel_e_publicada_nao_vao_para_a_api():
    qs = _qs(Gupy().url(_busca(nivel=["estagio"], publicada=86400)))
    assert set(qs) == {"jobName", "limit", "offset"}


# --- validação -------------------------------------------------------------

@pytest.mark.parametrize("kw, erro", [
    ({"modalidade": ["home office"]}, "modalidade desconhecido"),
    ({"palavra_chave": "  "}, "precisa de uma palavra_chave"),
])
def test_validar(kw, erro):
    with pytest.raises(ValueError, match=erro):
        Gupy().validar(_busca(**kw))


def test_validar_aceita_nivel_e_publicada_quaisquer():
    Gupy().validar(_busca(nivel=["diretor"], publicada="semana"))  # são ignorados, não é erro


# --- conversão -------------------------------------------------------------

def test_converter():
    vaga = Gupy().converter(RESPOSTA["data"][0])
    assert vaga["job_id"] == "gupy:12786122"
    assert vaga["url"] == "https://acme.gupy.io/job/eyJqb2JJZCI6MTI3ODYxMjJ9"
    assert vaga["titulo"] == "Estágio em Desenvolvimento Backend"
    assert vaga["empresa"] == "Acme Tecnologia"
    assert vaga["local"] == "São Paulo - SP"
    assert vaga["modalidade"] == "Híbrido"
    assert vaga["tipo_contrato"] == "Estágio"
    assert vaga["nivel"] == "Estágio"
    assert vaga["publicada_em"].startswith("2026-10-26")
    assert vaga["descricao"] == "Venha fazer parte do nosso time!\nRequisitos:\nPython\nSQL"


def test_converter_estagio_pelo_nome():
    vaga = Gupy().converter(RESPOSTA["data"][2])  # "Estagiário de Dados", tipo efetivo
    assert vaga["nivel"] == "Estágio"
    assert vaga["tipo_contrato"] == "Efetivo"


def test_converter_sem_cidade_e_tipo_pj():
    vaga = Gupy().converter(RESPOSTA["data"][3])
    assert vaga["local"] is None
    assert vaga["tipo_contrato"] == "PJ"
    assert vaga["nivel"] is None


# --- nada é descartado -----------------------------------------------------

def test_salva_tudo_mesmo_com_campos_de_filtro_preenchidos(caplog):
    busca = _busca(local="Campinas", modalidade=["presencial", "hibrido"],
                   nivel=["estagio"], publicada=3600)
    with caplog.at_level("INFO"):
        vagas = _listar(busca)
    assert [v["job_id"] for v in vagas] == [
        "gupy:12786122", "gupy:12785031", "gupy:12000001", "gupy:12000002",
    ]
    assert "nivel e publicada não são usados na Gupy" in caplog.text


def test_sem_nivel_nem_publicada_nao_avisa(caplog):
    with caplog.at_level("INFO"):
        _listar(_busca())
    assert "não são usados" not in caplog.text


# --- paginação -------------------------------------------------------------

def test_paginacao_ate_o_total():
    cliente = ClienteFalso(por_pagina=3)
    assert len(_listar(_busca(), cliente)) == 4
    assert [_qs(u)["offset"] for u in cliente.urls] == ["0", "3"]


def test_respeita_limite():
    cliente = ClienteFalso(por_pagina=3)
    assert len(_listar(_busca(), cliente, limite=2)) == 2
    assert len(cliente.urls) == 1


def test_resposta_vazia():
    vazia = copy.deepcopy(RESPOSTA)
    vazia["data"] = []
    assert _listar(_busca(), ClienteFalso(vazia)) == []
