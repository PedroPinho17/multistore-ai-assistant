"""Segurança na própria base de dados (precisa do Postgres: docker compose up -d).

Estes testes NÃO passam pelo validador de SQL: simulam o pior caso, em que
SQL malicioso chega à BD, e confirmam que o RLS e as permissões aguentam.
"""
import os

import psycopg
import pytest

from multistore_ai_assistant.db.query import run_query
from tests.conftest import IMPERADOR

pytestmark = pytest.mark.integration


def _db_available() -> bool:
    try:
        with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=3) as conn:
            return conn.execute("SELECT to_regclass('public.app_secret') IS NOT NULL").fetchone()[0]
    except Exception:
        return False


if not _db_available():
    pytest.skip("Base de dados indisponível ou sem as migrações aplicadas", allow_module_level=True)


@pytest.fixture(scope="module")
def owner():
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as conn:
        yield conn


@pytest.fixture(scope="module")
def users(owner):
    """Os perfis reais da tabela users (ids corretos, sejam quais forem)."""
    rows = owner.execute("SELECT username, role, brand_id, store_id FROM users").fetchall()
    return {u: {"username": u, "role": r, "brand_id": b, "store_id": s} for u, r, b, s in rows}


@pytest.fixture(scope="module")
def expected_stores(owner, users):
    total = owner.execute("SELECT count(*) FROM stores").fetchone()[0]
    brand = owner.execute("SELECT count(*) FROM stores WHERE brand_id = %s",
                          (users["gestor.burgerlab"]["brand_id"],)).fetchone()[0]
    return {"pedro": total, "gestor.burgerlab": brand, "gerente.maia": 1}


def count_stores(user) -> int:
    return run_query("SELECT count(DISTINCT store_id) FROM sales", user)[1][0][0]


# ---------- RLS por perfil ----------

@pytest.mark.parametrize("username", ["pedro", "gestor.burgerlab", "gerente.maia"])
def test_each_profile_sees_only_its_stores(users, expected_stores, username):
    assert count_stores(users[username]) == expected_stores[username]


def test_store_manager_sees_only_own_store_everywhere(users):
    loja = users["gerente.maia"]
    for table in ("sales", "stock", "employees", "transfers"):
        rows = run_query(f"SELECT DISTINCT store_id FROM {table} WHERE store_id IS NOT NULL", loja)[1]
        assert rows == [(loja["store_id"],)], table


@pytest.mark.parametrize("table", ["purchases", "purchase_lines", "suppliers"])
def test_only_imperador_sees_purchases(users, table):
    assert run_query(f"SELECT count(*) FROM {table}", users["gerente.maia"])[1][0][0] == 0
    assert run_query(f"SELECT count(*) FROM {table}", users["gestor.burgerlab"])[1][0][0] == 0
    assert run_query(f"SELECT count(*) FROM {table}", IMPERADOR)[1][0][0] > 0


def test_unknown_role_sees_nothing():
    ghost = {"role": "fantasma", "brand_id": None, "store_id": None}
    assert run_query("SELECT count(*) FROM sales", ghost)[1][0][0] == 0


# ---------- ataques ao contexto do RLS ----------

ATTACKS = {
    "set_config_cte": "WITH x AS MATERIALIZED (SELECT set_config('app.role','imperador',true) r) "
                      "SELECT count(DISTINCT store_id) FROM sales, x",
    "set_config_subquery": "SELECT (SELECT count(DISTINCT store_id) FROM sales "
                           "WHERE set_config('app.role','imperador',true) IS NOT NULL)",
    "forge_signature": "SELECT set_config('app.sig', 'x', true), (SELECT count(DISTINCT store_id) FROM sales)",
    "other_store": "WITH x AS MATERIALIZED (SELECT set_config('app.store_id','2',true) r) "
                   "SELECT count(*) FILTER (WHERE store_id = 2) FROM sales, x",
}


@pytest.mark.parametrize("sql", ATTACKS.values(), ids=ATTACKS.keys())
def test_changing_the_context_inside_a_query_does_not_escalate(users, sql):
    """Antes da correção, o gerente de loja via as 15 lojas com set_config()."""
    row = run_query(sql, users["gerente.maia"])[1][0]
    assert row[-1] in (0, 1)       # 0 = contexto inválido (fail-closed), 1 = só a sua loja


def test_signature_check_runs_in_the_database(owner):
    """Mesmo com o role certo, sem assinatura válida não se vê nada."""
    with psycopg.connect(os.environ["READONLY_DATABASE_URL"]) as conn:
        conn.execute("SELECT set_config('app.role', 'imperador', true)")
        assert conn.execute("SELECT count(*) FROM sales").fetchone()[0] == 0


# ---------- permissões do role 'assistente' ----------

@pytest.mark.parametrize("sql", [
    "SELECT key FROM app_secret",
    "SELECT password_hash FROM users",
    "SELECT nif FROM employees",
    "SELECT niss FROM employees",
    "SELECT address FROM employees",
    "SELECT birth_date FROM employees",
    "SELECT * FROM employees",
    "SELECT * FROM conversations",
    "SELECT * FROM messages",
], ids=lambda s: s.split("FROM")[0].replace("SELECT", "").strip() + "@" + s.split("FROM")[1].strip())
def test_private_data_is_not_readable(sql):
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        run_query(sql, IMPERADOR)


def test_allowed_employee_columns_are_readable():
    cols, _ = run_query("SELECT full_name, role, hourly_rate FROM employees LIMIT 1", IMPERADOR)
    assert cols == ["full_name", "role", "hourly_rate"]


@pytest.mark.parametrize("sql", [
    "INSERT INTO brands (name) VALUES ('hack')",
    "UPDATE products SET price = 0",
    "DELETE FROM sales WHERE false",
    "CREATE TABLE hack (id int)",
    "SELECT set_config('transaction_read_only', 'off', true)",   # sair do modo só de leitura
])
def test_read_only_role_cannot_write(sql):
    with pytest.raises(psycopg.Error):
        run_query(sql, IMPERADOR)


def test_security_definer_functions_are_pinned_to_public(owner):
    rows = owner.execute("""
        SELECT p.proname, p.proconfig FROM pg_proc p
        WHERE p.proname IN ('ctx_role', 'visible_store_ids') AND p.prosecdef""").fetchall()
    assert {r[0] for r in rows} == {"ctx_role", "visible_store_ids"}
    assert all("search_path=public" in (r[1] or []) for r in rows)


def test_views_respect_rls(owner):
    """As views usam security_invoker; sem isto ignoravam o RLS."""
    rows = owner.execute("""
        SELECT c.relname FROM pg_class c
        WHERE c.relkind = 'v' AND c.relnamespace = 'public'::regnamespace
          AND NOT coalesce('security_invoker=true' = ANY (c.reloptions), false)""").fetchall()
    assert rows == []
