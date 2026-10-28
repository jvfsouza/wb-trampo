from wb_trampo.parser import parse_detalhe, parse_lista


def test_parse_lista(html_lista):
    vagas = parse_lista(html_lista)
    assert [v["job_id"] for v in vagas] == ["4012345678", "4098765432", "4011112222"]
    assert vagas[0] == {
        "job_id": "4012345678",
        "titulo": "Desenvolvedor Python Júnior",
        "empresa": "Acme Tecnologia",
        "local": "São Paulo, SP",
        "publicada_em": "2026-10-20",
    }
    assert vagas[2]["publicada_em"] is None


def test_parse_lista_vazia():
    assert parse_lista("") == []
    assert parse_lista("<html><body>nada aqui</body></html>") == []


def test_parse_detalhe(html_detalhe):
    d = parse_detalhe(html_detalhe)
    assert d["nivel"] == "Assistente"
    assert d["tipo_contrato"] == "Tempo integral"
    assert d["area"] == "Tecnologia da informação"
    assert d["candidatos"] == "Mais de 100 candidaturas"
    assert d["descricao"].splitlines() == [
        "Sobre a vaga",
        "Procuramos pessoa desenvolvedora Python para atuar com APIs.",
        "Experiência com Django ou FastAPI",
        "Conhecimento em SQL",
    ]


def test_parse_detalhe_vazio():
    d = parse_detalhe("<html></html>")
    assert all(v is None for v in d.values())
