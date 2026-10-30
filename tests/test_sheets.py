"""Envio para o Google Sheets (Apps Script) com um script falso, sem internet."""

import logging
from datetime import date

import pytest

from wb_trampo import __main__ as cli
from wb_trampo import sheets
from wb_trampo.banco import Banco
from wb_trampo.config import GoogleSheets
from wb_trampo.sheets import LIMITE_CELULA, ErroSheets, enviar_novas, vagas_novas

HOJE = date(2026, 10, 27)
CONF = GoogleSheets(url_script="https://script.google.com/macros/s/X/exec", senha="segredo")


class ScriptFalso:
    """Imita o apps_script/Codigo.gs: aba por nome, sem repetir links."""

    def __init__(self, senha="segredo"):
        self.senha = senha
        self.abas = {}
        self.corpos = []

    def __call__(self, url, corpo):
        self.corpos.append(corpo)
        if corpo["senha"] != self.senha:
            return {"ok": False, "erro": "senha incorreta"}
        criada = corpo["aba"] not in self.abas
        aba = self.abas.setdefault(corpo["aba"], [corpo["cabecalho"]])
        col = corpo["cabecalho"].index("Link")
        existentes = {linha[col] for linha in aba[1:]}
        novas = [linha for linha in corpo["linhas"] if linha[col] not in existentes]
        aba.extend(novas)
        return {"ok": True, "aba": corpo["aba"], "criada": criada,
                "adicionadas": len(novas), "repetidas": len(corpo["linhas"]) - len(novas)}


def _vaga(n, **extra):
    return {
        "job_id": f"gupy:{n}", "site": "gupy", "titulo": f"Vaga {n}", "empresa": "ACME",
        "local": "São Paulo - SP", "modalidade": "Híbrido", "tipo_contrato": "Estágio",
        "url": f"https://acme.gupy.io/job/{n}", "descricao": "Texto", "nivel": "Estágio",
        "publicada_em": "2026-10-27 14:32", **extra,
    }


def _banco_com(tmp_path, *grupos):
    """Cada grupo de vagas vira uma execução."""
    banco = Banco(tmp_path / "vagas.db")
    for grupo in grupos:
        execucao = banco.iniciar_execucao()
        for vaga in grupo:
            banco.salvar(vaga, execucao)
    return banco


def test_envia_para_a_aba_do_dia(tmp_path):
    banco = _banco_com(tmp_path, [_vaga(1), _vaga(2, publicada_em=None)])
    script = ScriptFalso()

    assert enviar_novas(banco, CONF, postar=script, hoje=HOJE) == 2

    corpo = script.corpos[0]
    assert corpo["senha"] == "segredo" and corpo["aba"] == "2026-10-27 Gupy"
    aba = script.abas["2026-10-27 Gupy"]
    assert aba[0] == ["Título", "Empresa", "Site", "Local", "Modalidade", "Contrato", "Link", "Publicada em"]
    assert aba[1] == ["Vaga 1", "ACME", "gupy", "São Paulo - SP", "Híbrido", "Estágio",
                      "https://acme.gupy.io/job/1", "2026-10-27 14:32"]
    assert aba[2][-1] == ""  # sem data -> célula vazia
    assert "Texto" not in str(corpo)  # a descrição não é enviada


def test_mesmo_dia_acrescenta_sem_repetir(tmp_path, caplog):
    banco = _banco_com(tmp_path, [_vaga(1), _vaga(2)])
    script = ScriptFalso()
    enviar_novas(banco, CONF, postar=script, hoje=HOJE)

    execucao = banco.iniciar_execucao()
    banco.salvar(_vaga(3), execucao)
    assert enviar_novas(banco, CONF, postar=script, hoje=HOJE) == 1
    with caplog.at_level(logging.INFO):
        assert enviar_novas(banco, CONF, postar=script, hoje=HOJE) == 0
    assert "1 já estavam lá" in caplog.text

    links = [linha[6] for linha in script.abas["2026-10-27 Gupy"][1:]]
    assert links == [f"https://acme.gupy.io/job/{n}" for n in (1, 2, 3)]


def test_sem_vagas_novas_nao_envia(tmp_path):
    banco = _banco_com(tmp_path, [])

    def postar(url, corpo):
        raise AssertionError("não deveria enviar")

    assert enviar_novas(banco, CONF, postar=postar, hoje=HOJE) == 0


def test_um_aba_por_site(tmp_path):
    linkedin = {**_vaga(9), "job_id": "9", "site": "linkedin", "url": "https://www.linkedin.com/jobs/view/9/"}
    banco = _banco_com(tmp_path, [_vaga(1), linkedin, _vaga(2)])
    script = ScriptFalso()
    assert enviar_novas(banco, CONF, postar=script, hoje=HOJE) == 3
    assert {aba: len(linhas) - 1 for aba, linhas in script.abas.items()} == {
        "2026-10-27 Gupy": 2, "2026-10-27 LinkedIn": 1,
    }


def test_aba_usa_o_dia_da_busca(tmp_path):
    banco = _banco_com(tmp_path, [_vaga(1)])
    banco.con.execute("UPDATE execucoes SET iniciada_em = '2026-10-20 23:50:00'")
    script = ScriptFalso()
    enviar_novas(banco, CONF, postar=script)  # reenviado em outro dia: vai para a aba do dia da busca
    assert list(script.abas) == ["2026-10-20 Gupy"]


def test_senha_errada(tmp_path):
    banco = _banco_com(tmp_path, [_vaga(1)])
    with pytest.raises(ErroSheets, match="senha incorreta"):
        enviar_novas(banco, CONF, postar=ScriptFalso(senha="outra"), hoje=HOJE)


def test_filtro_sql_escolhe_o_que_vai_para_a_planilha(tmp_path):
    banco = _banco_com(tmp_path, [_vaga(1, tipo_contrato="Efetivo"), _vaga(2), _vaga(3, titulo="Vaga Sênior")])
    script = ScriptFalso()
    filtro = "tipo_contrato = 'Estágio' AND titulo NOT LIKE '%Sênior%'"
    assert enviar_novas(banco, CONF, postar=script, hoje=HOJE, filtro_sql=filtro) == 1
    assert [linha[0] for linha in script.abas["2026-10-27 Gupy"][1:]] == ["Vaga 2"]


def test_filtro_que_zera_tudo_nao_chama_o_script(tmp_path, caplog):
    banco = _banco_com(tmp_path, [_vaga(1)])

    def postar(url, corpo):
        raise AssertionError("não deveria enviar")

    with caplog.at_level(logging.INFO):
        assert enviar_novas(banco, CONF, postar=postar, hoje=HOJE, filtro_sql="modalidade = 'Remoto'") == 0
    assert "1 vagas novas, 0 passaram no filtro" in caplog.text


def test_filtro_nao_afeta_o_banco(tmp_path):
    banco = _banco_com(tmp_path, [_vaga(1), _vaga(2, tipo_contrato="Efetivo")])
    vagas_novas(banco, filtro_sql="tipo_contrato = 'Estágio'")
    assert len(vagas_novas(banco)) == 2


def test_so_vagas_da_ultima_execucao(tmp_path):
    banco = _banco_com(tmp_path, [_vaga(1)], [_vaga(2)])
    assert [linha[0] for linha in vagas_novas(banco)] == ["Vaga 2"]


def test_corta_texto_enorme_e_evita_formula(tmp_path):
    banco = _banco_com(tmp_path, [_vaga(1, titulo="x" * (LIMITE_CELULA + 10), empresa="=HYPERLINK(1)")])
    linha = vagas_novas(banco)[0]
    assert len(linha[0]) == LIMITE_CELULA + 1 and linha[0].endswith("…")
    assert linha[1] == "'=HYPERLINK(1)"


class Resp:
    def __init__(self, status, corpo=None):
        self.status_code = status
        self.corpo = corpo

    def json(self):
        if self.corpo is None:
            raise ValueError("não é JSON")
        return self.corpo


@pytest.mark.parametrize("resposta, erro", [
    (Resp(200), "não respondeu com JSON.*Qualquer pessoa"),
    (Resp(404), "não encontrado"),
    (Resp(500), "HTTP 500"),
])
def test_postar_erros(monkeypatch, resposta, erro):
    monkeypatch.setattr(sheets.requests, "post", lambda *a, **k: resposta)
    with pytest.raises(ErroSheets, match=erro):
        sheets._postar(CONF.url_script, {})


def test_postar_ok(monkeypatch):
    enviados = []

    def post(url, data, timeout, headers):
        enviados.append((url, data))
        return Resp(200, {"ok": True})

    monkeypatch.setattr(sheets.requests, "post", post)
    assert sheets._postar(CONF.url_script, {"a": 1}) == {"ok": True}
    assert enviados == [(CONF.url_script, '{"a": 1}')]


def test_falha_no_sheets_nao_perde_o_excel(tmp_path, monkeypatch, caplog):
    """`buscar`: se o envio falhar, o Excel é gerado e o código de saída é 1."""
    config = tmp_path / "config.toml"
    config.write_text('[[buscas]]\nsite = "gupy"\npalavra_chave = "py"\n', encoding="utf-8")
    (tmp_path / "google_sheets.toml").write_text(
        'url_script = "https://script.google.com/macros/s/X/exec"\nsenha = "segredo"\n', encoding="utf-8"
    )

    def executar_falso(config, banco, cliente, buscar_descricao=None):
        execucao = banco.iniciar_execucao()
        banco.salvar(_vaga(1), execucao)
        banco.finalizar_execucao(execucao)

        class Resumo:
            vistas = novas = 1
        return Resumo()

    def post_sem_internet(*a, **k):
        raise sheets.requests.ConnectionError("sem internet")

    monkeypatch.setattr(cli, "executar", executar_falso)
    monkeypatch.setattr(sheets.requests, "post", post_sem_internet)
    excel = tmp_path / "vagas.xlsx"
    with caplog.at_level(logging.INFO):
        codigo = cli.main(["--banco", str(tmp_path / "vagas.db"), "--logs", str(tmp_path / "logs"),
                           "buscar", "--config", str(config), "--excel", str(excel)])
    assert codigo == 1
    assert excel.exists()
    assert "sem internet" in caplog.text and "enviar-sheets" in caplog.text
