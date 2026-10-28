"""Cliente HTTP educado: pausa entre requisições (maior no LinkedIn), teto de requisições por
execução e para logo quando o site recusa, em vez de insistir."""

from __future__ import annotations

import json
import logging
import random
import time
from collections import Counter
from collections.abc import Callable
from urllib.parse import urlsplit

import requests

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
}

HOST_LINKEDIN = "www.linkedin.com"
STATUS_RECUSA = 999  # código que o LinkedIn usa para "acesso negado a robôs": para na hora
STATUS_LIMITE = 429  # muitas requisições: espera e tenta mais um pouco
ESPERA_MAXIMA_S = 600  # teto para o Retry-After pedido pelo site


class Bloqueado(Exception):
    """O site recusou as requisições. O robô para em vez de insistir."""


class LimiteRequisicoes(Exception):
    """Atingiu max_requisicoes nesta execução (fim normal, não é erro)."""


class NaoEncontrado(Exception):
    """A vaga não existe mais (404)."""


def _host(url: str) -> str:
    return urlsplit(url).hostname or ""


def _retry_after(resp) -> float | None:
    valor = (getattr(resp, "headers", None) or {}).get("Retry-After")
    if valor and str(valor).strip().isdigit():
        return min(float(valor), ESPERA_MAXIMA_S)
    return None


class Cliente:
    def __init__(
        self,
        pausa_min_s: float = 2.0,
        pausa_max_s: float = 5.0,
        esperas_s: tuple[float, ...] = (60, 180),
        session: requests.Session | None = None,
        dormir: Callable[[float], None] = time.sleep,
        pausas_por_host: dict[str, tuple[float, float]] | None = None,
        max_requisicoes: int = 0,
        esperas_erro_s: tuple[float, ...] = (10, 30, 60),
        agora: Callable[[], float] = time.monotonic,
    ) -> None:
        """esperas_s: esperas após HTTP 429 (sem Retry-After); esperas_erro_s: após 5xx/erro de rede.
        max_requisicoes = 0 significa sem teto."""
        self.pausa_padrao = (pausa_min_s, pausa_max_s)
        self.pausas_por_host = pausas_por_host or {}
        self.esperas_s = esperas_s
        self.esperas_erro_s = esperas_erro_s
        self.max_requisicoes = max_requisicoes
        self.session = session or requests.Session()
        self.session.headers.update(HEADERS)
        self.dormir = dormir
        self.agora = agora
        self.requisicoes = 0
        self.por_host: Counter[str] = Counter()
        self._ultima: dict[str, float] = {}  # host -> instante da última requisição

    def pausa(self, host: str) -> tuple[float, float]:
        return self.pausas_por_host.get(host, self.pausa_padrao)

    def _pausar(self, host: str) -> None:
        """Espera o que falta da pausa desde a última requisição a este mesmo host."""
        if host not in self._ultima:
            return
        sorteada = random.uniform(*self.pausa(host))
        falta = sorteada - (self.agora() - self._ultima[host])
        if falta > 0:
            log.debug("pausa de %.1fs (%s)", falta, host)
            self.dormir(falta)

    def _requisitar(self, url: str, host: str):
        if self.max_requisicoes and self.requisicoes >= self.max_requisicoes:
            raise LimiteRequisicoes(f"teto de {self.max_requisicoes} requisições atingido")
        self.requisicoes += 1
        self.por_host[host] += 1
        try:
            return self.session.get(url, timeout=20)
        finally:
            self._ultima[host] = self.agora()

    def get(self, url: str) -> str:
        host = _host(url)
        self._pausar(host)
        tentativas_429 = tentativas_erro = 0
        while True:
            inicio = time.perf_counter()
            log.debug("GET %s", url)
            try:
                resp = self._requisitar(url, host)
            except requests.RequestException as erro:
                problema, esperas, n = f"erro de rede: {erro}", self.esperas_erro_s, tentativas_erro
                tentativas_erro += 1
                log.warning("Falha de rede em %s: %s", url, erro)
                espera = None
            else:
                log.debug("HTTP %d, %d bytes, %.2fs", resp.status_code, len(resp.text),
                          time.perf_counter() - inicio)
                if resp.status_code == 200:
                    return resp.text
                if resp.status_code == 404:
                    raise NaoEncontrado(url)
                if resp.status_code == STATUS_RECUSA:
                    raise Bloqueado(
                        f"O site recusou o acesso (HTTP {STATUS_RECUSA}) em {url}. "
                        "Espere algumas horas antes de rodar de novo."
                    )
                if resp.status_code == STATUS_LIMITE:
                    problema, esperas, n = f"HTTP {STATUS_LIMITE}", self.esperas_s, tentativas_429
                    tentativas_429 += 1
                    espera = _retry_after(resp)
                elif resp.status_code >= 500:
                    problema, esperas, n = f"HTTP {resp.status_code}", self.esperas_erro_s, tentativas_erro
                    tentativas_erro += 1
                    espera = None
                else:
                    log.error("Resposta inesperada HTTP %d em %s", resp.status_code, url)
                    resp.raise_for_status()
                    raise RuntimeError(f"HTTP {resp.status_code} em {url}")

            if n >= len(esperas):
                raise Bloqueado(
                    f"O site recusou as requisições ({problema}) em {url}. "
                    "Espere algumas horas antes de rodar de novo ou reduza max_vagas_por_busca."
                )
            if espera is None:
                espera = esperas[n]
            log.warning("%s; aguardando %.0fs antes de tentar de novo (%d/%d)",
                        problema, espera, n + 1, len(esperas))
            self.dormir(espera)

    def get_json(self, url: str):
        texto = self.get(url)
        try:
            return json.loads(texto)
        except json.JSONDecodeError as erro:
            raise ValueError(f"Resposta não é JSON em {url}: {texto[:200]!r}") from erro

    def resumo(self) -> str:
        detalhes = ", ".join(f"{host} {n}" for host, n in self.por_host.most_common())
        return f"{self.requisicoes} ({detalhes})" if detalhes else "0"
