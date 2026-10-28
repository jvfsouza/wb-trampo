"""Armazenamento das vagas em SQLite."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from .urls import url_vaga

SCHEMA = """
CREATE TABLE IF NOT EXISTS execucoes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    iniciada_em   TEXT NOT NULL,
    terminada_em  TEXT
);

CREATE TABLE IF NOT EXISTS vagas (
    job_id             TEXT PRIMARY KEY,  -- LinkedIn: só o número; outros sites: "site:número"
    site               TEXT NOT NULL DEFAULT 'linkedin',
    titulo             TEXT,
    empresa            TEXT,
    local              TEXT,
    modalidade         TEXT,
    nivel              TEXT,
    tipo_contrato      TEXT,
    area               TEXT,
    publicada_em       TEXT,
    candidatos         TEXT,
    url                TEXT NOT NULL UNIQUE,
    descricao          TEXT,
    busca              TEXT,
    primeiro_visto_em  TEXT NOT NULL,
    visto_em           TEXT NOT NULL,
    execucao           INTEGER REFERENCES execucoes(id)  -- execução em que a vaga apareceu pela 1ª vez
);
"""

CAMPOS = [
    "titulo", "empresa", "local", "modalidade", "nivel", "tipo_contrato",
    "area", "publicada_em", "candidatos", "descricao", "busca",
]


def _agora() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


class Banco:
    def __init__(self, caminho: str | Path = "data/vagas.db") -> None:
        if str(caminho) != ":memory:":
            Path(caminho).parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(caminho)
        self.con.executescript(SCHEMA)
        self._migrar()

    def _migrar(self) -> None:
        """Atualiza bancos criados por versões anteriores."""
        colunas = {linha[1] for linha in self.con.execute("PRAGMA table_info(vagas)")}
        if "site" not in colunas:
            with self.con:
                self.con.execute("ALTER TABLE vagas ADD COLUMN site TEXT NOT NULL DEFAULT 'linkedin'")

    def fechar(self) -> None:
        self.con.close()

    def iniciar_execucao(self) -> int:
        with self.con:
            cur = self.con.execute("INSERT INTO execucoes (iniciada_em) VALUES (?)", (_agora(),))
        return cur.lastrowid

    def finalizar_execucao(self, execucao: int) -> None:
        with self.con:
            self.con.execute(
                "UPDATE execucoes SET terminada_em = ? WHERE id = ?", (_agora(), execucao)
            )

    def ultima_execucao(self) -> int | None:
        return self.con.execute("SELECT MAX(id) FROM execucoes").fetchone()[0]

    def inicio_ultima_execucao(self) -> datetime | None:
        """Quando a última execução começou (hora local), ou None se nunca rodou."""
        linha = self.con.execute("SELECT iniciada_em FROM execucoes ORDER BY id DESC LIMIT 1").fetchone()
        return datetime.fromisoformat(linha[0]) if linha else None

    def existe(self, job_id: str) -> bool:
        cur = self.con.execute("SELECT 1 FROM vagas WHERE job_id = ?", (job_id,))
        return cur.fetchone() is not None

    def marcar_visto(self, job_id: str) -> None:
        with self.con:
            self.con.execute("UPDATE vagas SET visto_em = ? WHERE job_id = ?", (_agora(), job_id))

    def salvar(self, vaga: dict, execucao: int | None = None) -> None:
        """Insere a vaga ou, se já existir, atualiza visto_em e preenche campos que estavam vazios."""
        agora = _agora()
        job_id = str(vaga["job_id"])
        valores = {c: vaga.get(c) for c in CAMPOS}
        site = vaga.get("site") or "linkedin"
        # o LinkedIn não manda url (montamos a partir do id); os outros sites mandam
        url = vaga.get("url") or url_vaga(job_id)
        colunas = ["job_id", "site", *CAMPOS, "url", "primeiro_visto_em", "visto_em", "execucao"]
        params = [job_id, site, *valores.values(), url, agora, agora, execucao]
        preencher = ", ".join(f"{c} = COALESCE(vagas.{c}, excluded.{c})" for c in CAMPOS)
        with self.con:
            self.con.execute(
                f"INSERT INTO vagas ({', '.join(colunas)}) "
                f"VALUES ({', '.join('?' * len(colunas))}) "
                f"ON CONFLICT(job_id) DO UPDATE SET visto_em = excluded.visto_em, {preencher}",
                params,
            )

    def contar(self) -> int:
        return self.con.execute("SELECT COUNT(*) FROM vagas").fetchone()[0]
