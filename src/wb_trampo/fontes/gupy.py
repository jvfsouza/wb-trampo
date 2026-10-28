"""Gupy: busca do portal público (portal.gupy.io), que reúne vagas de milhares de empresas.

A API do portal aceita palavra-chave (procurada no NOME da vaga), estado, cidade e uma
modalidade. Tudo o que ela retornar é salvo: o robô não descarta nada. Nível e data de
publicação não existem como filtro na API, então ficam para o usuário filtrar na planilha.
A API devolve no máximo 100 vagas por busca.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from datetime import datetime
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from ..parser import html_para_texto
from ..urls import MODALIDADE, _normalizar

if TYPE_CHECKING:
    from ..cliente import Cliente
    from ..config import Busca

log = logging.getLogger(__name__)

API = "https://portal.gupy.io/api/job-search/jobs"
POR_PAGINA = 50
TETO = 100  # a API não passa disso, mesmo havendo mais vagas

# sigla -> nome oficial (como a API espera em `state`)
ESTADOS = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas", "BA": "Bahia",
    "CE": "Ceará", "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás",
    "MA": "Maranhão", "MT": "Mato Grosso", "MS": "Mato Grosso do Sul", "MG": "Minas Gerais",
    "PA": "Pará", "PB": "Paraíba", "PR": "Paraná", "PE": "Pernambuco", "PI": "Piauí",
    "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte", "RS": "Rio Grande do Sul",
    "RO": "Rondônia", "RR": "Roraima", "SC": "Santa Catarina", "SP": "São Paulo",
    "SE": "Sergipe", "TO": "Tocantins",
}
_ESTADO_POR_TEXTO = {
    **{_normalizar(sigla): nome for sigla, nome in ESTADOS.items()},
    **{_normalizar(nome): nome for nome in ESTADOS.values()},
}
_SIGLA_POR_NOME = {nome: sigla for sigla, nome in ESTADOS.items()}

TIPOS = {
    "vacancy_type_internship": "Estágio",
    "vacancy_type_effective": "Efetivo",
    "vacancy_legal_entity": "PJ",
    "vacancy_type_trainee": "Trainee",
    "vacancy_type_temporary": "Temporário",
    "vacancy_type_apprentice": "Aprendiz",
    "vacancy_type_autonomous": "Autônomo",
    "vacancy_type_outsource": "Terceirizado",
    "vacancy_type_talent_pool": "Banco de talentos",
}

# modalidade da API <-> nome usado no config; e o rótulo salvo no banco
MODALIDADE_API = {"on-site": "presencial", "hybrid": "hibrido", "remote": "remoto"}
API_MODALIDADE = {v: k for k, v in MODALIDADE_API.items()}
ROTULO_MODALIDADE = {"presencial": "Presencial", "hibrido": "Híbrido", "remoto": "Remoto"}

PALAVRAS_ESTAGIO = {"estagio", "estagiario", "estagiaria", "intern", "internship"}


def _palavras(texto: str | None) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", _normalizar(texto or "")))


def estado(local: str) -> str | None:
    """Nome oficial do estado se `local` for um estado (nome ou sigla), senão None."""
    return _ESTADO_POR_TEXTO.get(_normalizar(local)) if local else None


def _data(item: dict) -> datetime | None:
    bruto = item.get("publishedDate")
    if not bruto:
        return None
    try:
        return datetime.fromisoformat(bruto.replace("Z", "+00:00"))
    except ValueError:
        return None


def _eh_estagio(item: dict) -> bool:
    return item.get("type") == "vacancy_type_internship" or bool(
        _palavras(item.get("name")) & PALAVRAS_ESTAGIO
    )


class Gupy:
    nome = "gupy"

    # --- validação e URL ---------------------------------------------------

    def validar(self, busca: Busca) -> None:
        if not busca.palavra_chave.strip():
            raise ValueError("a Gupy precisa de uma palavra_chave")
        for m in busca.modalidade:
            if _normalizar(m) not in MODALIDADE:
                raise ValueError(
                    f"modalidade desconhecido: {m!r}. Use um de: {', '.join(sorted(MODALIDADE))}"
                )

    def parametros(self, busca: Busca, offset: int = 0) -> dict[str, str | int]:
        params: dict[str, str | int] = {"jobName": busca.palavra_chave.strip()}
        if busca.local:
            uf = estado(busca.local)
            if uf:
                params["state"] = uf
            else:
                params["city"] = busca.local.strip()  # a API exige o nome com acento
        if len(busca.modalidade) == 1:
            params["workplaceType"] = API_MODALIDADE[_normalizar(busca.modalidade[0])]
        params["limit"] = POR_PAGINA
        params["offset"] = offset
        return params

    def url(self, busca: Busca, offset: int = 0) -> str:
        return f"{API}?{urlencode(self.parametros(busca, offset))}"

    # --- conversão ---------------------------------------------------------

    def converter(self, item: dict) -> dict:
        cidade = item.get("city") or ""
        uf = _SIGLA_POR_NOME.get(item.get("state") or "", item.get("state") or "")
        publicada = _data(item)
        modalidade = MODALIDADE_API.get(item.get("workplaceType"))
        url = (item.get("jobUrl") or "").split("?")[0] or None
        return {
            "job_id": f"gupy:{item['id']}",
            "url": url,
            "titulo": (item.get("name") or "").strip() or None,
            "empresa": item.get("careerPageName") or None,
            "local": " - ".join(p for p in (cidade, uf) if p) or None,
            "modalidade": ROTULO_MODALIDADE.get(modalidade),
            "tipo_contrato": TIPOS.get(item.get("type"), item.get("type")),
            "nivel": "Estágio" if _eh_estagio(item) else None,
            "publicada_em": publicada.astimezone().strftime("%Y-%m-%d %H:%M") if publicada else None,
            "descricao": html_para_texto(item.get("description")),
        }

    # --- coleta ------------------------------------------------------------

    def listar(self, busca: Busca, cliente: Cliente, limite: int) -> Iterator[dict]:
        log.debug("Parâmetros Gupy: %s", self.parametros(busca))
        if busca.nivel or (busca.publicada is not None and busca.publicada != ""):
            log.info(
                "  nivel e publicada não são usados na Gupy: todas as vagas retornadas são salvas "
                "(filtre pela planilha: colunas Contrato, Nível e Publicada em)."
            )

        entregues = 0
        offset = 0
        pagina = 1
        while entregues < limite:
            log.info("  Página %d (vagas %d em diante)...", pagina, offset + 1)
            dados = cliente.get_json(self.url(busca, offset))
            itens = dados.get("data") or []
            total = (dados.get("pagination") or {}).get("total") or 0
            if pagina == 1:
                log.info("  A Gupy retornou %d vagas para '%s'.", total, busca.palavra_chave)
                if total >= TETO:
                    log.warning(
                        "  A Gupy só mostra %d vagas por busca; pode haver mais. "
                        "Use uma palavra-chave mais específica ou filtre por estado.", TETO,
                    )
            if not itens:
                log.info("  Fim dos resultados.")
                return

            for item in itens:
                yield self.converter(item)
                entregues += 1
                if entregues >= limite:
                    log.info("  Limite de %d vagas por busca atingido.", limite)
                    return

            offset += len(itens)
            pagina += 1
            if offset >= total:
                log.info("  Fim dos resultados.")
                return

    def detalhar(self, vaga: dict, cliente: Cliente) -> dict:
        return {}  # a lista da Gupy já traz descrição e demais dados
