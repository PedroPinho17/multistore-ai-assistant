"""Migrações na BD real: idempotentes e invisíveis ao role do LLM."""
import os

import psycopg
import pytest

from multistore_ai_assistant.db import migrate as mg
from multistore_ai_assistant.db.query import IMPERADOR, run_query

pytestmark = pytest.mark.integration

try:
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=3) as _c:
        _ok = _c.execute("SELECT to_regclass('public.sales') IS NOT NULL").fetchone()[0]
except Exception:
    _ok = False
if not _ok:
    pytest.skip("Base de dados indisponível", allow_module_level=True)


def test_second_run_applies_nothing():
    mg.migrate()
    assert mg.migrate() == []
    assert all(state == "aplicada" for _, state in mg.status())


def test_every_project_migration_is_recorded():
    with psycopg.connect(os.environ["DATABASE_URL"]) as c:
        recorded = {v for (v,) in c.execute("SELECT version FROM schema_migrations")}
    assert {m.version for m in mg.discover()} <= recorded


def test_llm_role_cannot_read_the_migrations_table():
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        run_query("SELECT * FROM schema_migrations", IMPERADOR)
