"""Migrações da base de dados (``db/migrations``), no estilo do Flyway.

- ``V001__descricao.sql``: versionadas. Correm **uma vez**, por ordem, cada uma
  numa transação. Mudar uma já aplicada não a volta a correr (gera um aviso):
  uma alteração nova é sempre um ficheiro novo.
- ``R__descricao.sql``: repetíveis (permissões, vistas). Correm depois das
  versionadas e de novo sempre que o conteúdo (checksum) muda.

Uma linha ``-- migrate: no-transaction`` no ficheiro corre-o fora de uma
transação, instrução a instrução (precisa disso, p.ex., ``REINDEX DATABASE``).

O registo fica em ``schema_migrations``; um advisory lock impede dois
arranques de migrar ao mesmo tempo.

Uso:  python -m multistore_ai_assistant.db.migrate            # aplica o que falta
      python -m multistore_ai_assistant.db.migrate --status   # só mostra o estado
"""
import hashlib
import logging
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("multistore")

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "db" / "migrations"
VERSIONED = re.compile(r"^V(\d{3,})__([a-z0-9_]+)\.sql$")
REPEATABLE = re.compile(r"^R__([a-z0-9_]+)\.sql$")
LOCK_ID = 7_204_311                # chave do pg_advisory_lock (qualquer número fixo)
NO_TRANSACTION = "-- migrate: no-transaction"

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
  version     text PRIMARY KEY,          -- '001', '002', ... ou 'R__readonly'
  description text NOT NULL,
  checksum    text NOT NULL,
  applied_at  timestamptz NOT NULL DEFAULT now()
)"""


@dataclass(frozen=True)
class Migration:
    version: str            # "001" (versionada) ou "R__readonly" (repetível)
    description: str
    path: Path
    repeatable: bool

    @property
    def sql(self) -> str:
        return self.path.read_text(encoding="utf-8")

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.sql.replace("\r\n", "\n").encode()).hexdigest()[:16]

    @property
    def transactional(self) -> bool:
        return NO_TRANSACTION not in self.sql


def discover(directory: Path = MIGRATIONS_DIR) -> list[Migration]:
    """Versionadas por número, depois as repetíveis por nome. Nomes inválidos dão erro."""
    versioned, repeatable = [], []
    for path in sorted(directory.glob("*.sql")):
        if m := VERSIONED.match(path.name):
            versioned.append(Migration(m.group(1), m.group(2).replace("_", " "), path, False))
        elif m := REPEATABLE.match(path.name):
            repeatable.append(Migration(f"R__{m.group(1)}", m.group(1).replace("_", " "), path, True))
        else:
            raise ValueError(f"Nome de migração inválido: {path.name} (usa V001__nome.sql ou R__nome.sql)")
    versions = [m.version for m in versioned]
    if len(set(versions)) != len(versions):
        raise ValueError(f"Versões repetidas em {directory}: {versions}")
    return sorted(versioned, key=lambda m: int(m.version)) + repeatable


def applied(conn) -> dict[str, str]:
    """``{versão: checksum}`` do que já foi aplicado."""
    conn.execute(CREATE_TABLE)
    return dict(conn.execute("SELECT version, checksum FROM schema_migrations").fetchall())


def pending(migrations: list[Migration], done: dict[str, str]) -> list[Migration]:
    """Versionadas ainda não aplicadas + repetíveis novas ou com conteúdo diferente."""
    out = []
    for m in migrations:
        if m.repeatable:
            if done.get(m.version) != m.checksum:
                out.append(m)
        elif m.version not in done:
            out.append(m)
        elif done[m.version] != m.checksum:
            log.warning("A migração %s mudou depois de aplicada: não volta a correr. "
                        "Cria uma migração nova para a alteração.", m.path.name)
    return out


def split_statements(sql: str) -> list[str]:
    """Separa por ``;`` no fim da linha (ficheiros sem transação não usam blocos ``$$``)."""
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    return [st.strip() for st in "\n".join(lines).split(";") if st.strip()]


def _apply(conn, m: Migration) -> None:
    record = ("INSERT INTO schema_migrations (version, description, checksum) VALUES (%s, %s, %s) "
              "ON CONFLICT (version) DO UPDATE SET checksum = EXCLUDED.checksum, applied_at = now()")
    if m.transactional:
        with conn.transaction():
            conn.execute(m.sql)
            conn.execute(record, (m.version, m.description, m.checksum))
    else:
        # Várias instruções num só execute formam um bloco implícito: corre uma a uma
        for statement in split_statements(m.sql):
            conn.execute(statement)
        conn.execute(record, (m.version, m.description, m.checksum))


def migrate(url: str | None = None, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Aplica as migrações em falta; devolve os nomes dos ficheiros aplicados."""
    migrations = discover(directory)
    with psycopg.connect(url or os.environ["DATABASE_URL"], autocommit=True) as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (LOCK_ID,))
        try:
            todo = pending(migrations, applied(conn))
            for m in todo:
                log.info("A aplicar %s", m.path.name)
                _apply(conn, m)
            # A tabela de controlo nunca é legível pelo role do LLM
            if conn.execute("SELECT 1 FROM pg_roles WHERE rolname = 'assistente'").fetchone():
                conn.execute("REVOKE ALL ON schema_migrations FROM assistente")
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_ID,))
    return [m.path.name for m in todo]


def status(url: str | None = None, directory: Path = MIGRATIONS_DIR) -> list[tuple[str, str]]:
    """``[(ficheiro, estado)]`` com estado ``aplicada``, ``pendente`` ou ``alterada``."""
    migrations = discover(directory)
    with psycopg.connect(url or os.environ["DATABASE_URL"], autocommit=True) as conn:
        done = applied(conn)
    out = []
    for m in migrations:
        if m.version not in done:
            state = "pendente"
        elif done[m.version] != m.checksum:
            state = "pendente (mudou)" if m.repeatable else "alterada depois de aplicada"
        else:
            state = "aplicada"
        out.append((m.path.name, state))
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if "--status" in sys.argv[1:]:
        for name, state in status():
            print(f"  {state:<30} {name}")
    else:
        done_now = migrate()
        print(f"OK migrações: {len(done_now)} aplicada(s)" + (f" ({', '.join(done_now)})" if done_now else ""))
