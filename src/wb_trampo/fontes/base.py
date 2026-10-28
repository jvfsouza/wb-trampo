"""Interface que cada site precisa seguir."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from ..cliente import Cliente
    from ..config import Busca


class Fonte(Protocol):
    nome: str

    def validar(self, busca: Busca) -> None:
        """Levanta ValueError com mensagem clara se a busca não servir para este site."""

    def listar(self, busca: Busca, cliente: Cliente, limite: int) -> Iterator[dict]:
        """Gera as vagas encontradas (já filtradas), no máximo `limite`.

        Cada vaga é um dict com pelo menos `job_id`; pode ter `url`, `titulo`, `empresa` etc.
        """

    def detalhar(self, vaga: dict, cliente: Cliente) -> dict:
        """Busca dados extras de uma vaga nova (ex.: descrição). Retorna {} se não houver."""
