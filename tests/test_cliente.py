import pytest

from wb_trampo.cliente import Bloqueado, Cliente, LimiteRequisicoes, NaoEncontrado

LINKEDIN = "https://www.linkedin.com/jobs-guest/x"
GUPY = "https://portal.gupy.io/api/job-search/jobs"


class Resp:
    def __init__(self, status, text="", headers=None):
        self.status_code = status
        self.text = text
        self.headers = headers or {}

    def raise_for_status(self):
        raise RuntimeError(f"HTTP {self.status_code}")


class SessaoFalsa:
    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.headers = {}
        self.urls = []

    @property
    def chamadas(self):
        return len(self.urls)

    def get(self, url, timeout):
        self.urls.append(url)
        return self.respostas.pop(0)


class Relogio:
    """Relógio falso: dormir avança o tempo."""

    def __init__(self):
        self.t = 1000.0
        self.esperas = []

    def agora(self):
        return self.t

    def dormir(self, s):
        self.esperas.append(s)
        self.t += s


def _cliente(respostas, **extra):
    relogio = Relogio()
    sessao = SessaoFalsa(respostas)
    opcoes = dict(esperas_s=(60, 180), esperas_erro_s=(10, 30),
                  pausas_por_host={"www.linkedin.com": (8, 15)})
    opcoes.update(extra)
    c = Cliente(2, 5, session=sessao, dormir=relogio.dormir, agora=relogio.agora, **opcoes)
    return c, sessao, relogio


def test_429_tenta_de_novo_com_espera_longa():
    c, _, relogio = _cliente([Resp(429), Resp(200, "ok")])
    assert c.get(LINKEDIN) == "ok"
    assert relogio.esperas == [60]  # primeira requisição não tem pausa, só a espera do 429


def test_429_respeita_retry_after():
    c, _, relogio = _cliente([Resp(429, headers={"Retry-After": "5"}), Resp(200, "ok")])
    assert c.get(LINKEDIN) == "ok"
    assert relogio.esperas == [5]


def test_429_desiste_depois_de_2_tentativas():
    c, sessao, relogio = _cliente([Resp(429), Resp(429), Resp(429)])
    with pytest.raises(Bloqueado, match="HTTP 429"):
        c.get(LINKEDIN)
    assert sessao.chamadas == 3
    assert relogio.esperas == [60, 180]


def test_999_para_na_hora():
    c, sessao, relogio = _cliente([Resp(999)])
    with pytest.raises(Bloqueado, match="HTTP 999"):
        c.get(LINKEDIN)
    assert sessao.chamadas == 1 and relogio.esperas == []


def test_5xx_usa_esperas_de_erro():
    c, _, relogio = _cliente([Resp(503), Resp(200, "ok")])
    assert c.get(GUPY) == "ok"
    assert relogio.esperas == [10]


def test_404_vira_nao_encontrado():
    c, _, _ = _cliente([Resp(404)])
    with pytest.raises(NaoEncontrado):
        c.get(LINKEDIN)


def test_pausa_por_site():
    c, _, relogio = _cliente([Resp(200)] * 4)
    c.get(LINKEDIN)
    c.get(LINKEDIN)
    c.get(GUPY)  # primeira na Gupy: não espera
    c.get(GUPY)
    linkedin, gupy = relogio.esperas
    assert 8 <= linkedin <= 15
    assert 2 <= gupy <= 5


def test_pausa_conta_o_tempo_desde_a_ultima_do_mesmo_site():
    c, _, relogio = _cliente([Resp(200)] * 3)
    c.get(LINKEDIN)
    relogio.t += 6  # ex.: tempo gasto com a Gupy no meio
    c.get(LINKEDIN)
    assert 2 <= relogio.esperas[0] <= 9  # só o que falta da pausa de 8–15 s
    relogio.t += 20  # já passou mais que a pausa máxima
    c.get(LINKEDIN)
    assert len(relogio.esperas) == 1


def test_teto_de_requisicoes():
    c, sessao, _ = _cliente([Resp(200)] * 3, max_requisicoes=2)
    c.get(GUPY)
    c.get(GUPY)
    with pytest.raises(LimiteRequisicoes):
        c.get(GUPY)
    assert sessao.chamadas == 2


def test_contagem_por_site():
    c, _, _ = _cliente([Resp(200)] * 3)
    c.get(LINKEDIN)
    c.get(LINKEDIN)
    c.get(GUPY)
    assert c.resumo() == "3 (www.linkedin.com 2, portal.gupy.io 1)"
