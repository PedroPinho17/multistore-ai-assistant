"""Regressões dos 6 problemas encontrados na revisão (BD real)."""
import os
from datetime import date, timedelta
from pathlib import Path

import psycopg
import pytest

from multistore_ai_assistant.api import conversations as conv
from multistore_ai_assistant.data import generate_activity
from multistore_ai_assistant.db.query import IMPERADOR, run_query

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]

try:
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=3) as _c:
        _ok = _c.execute("SELECT to_regclass('public.app_secret') IS NOT NULL").fetchone()[0]
except Exception:
    _ok = False
if not _ok:
    pytest.skip("Base de dados indisponível", allow_module_level=True)


@pytest.fixture(scope="module")
def brands():
    with psycopg.connect(os.environ["DATABASE_URL"]) as c:
        return dict(c.execute("SELECT id, name FROM brands ORDER BY id").fetchall())


def marca(brand_id):
    return {"role": "marca", "brand_id": brand_id, "store_id": None}


# ---------- 1. Respostas com erro não viram memória nem exemplos ----------

def test_failed_answer_is_not_used_as_history():
    cid = conv.create_conversation("gerente.maia", "teste erro")
    try:
        conv.add_message(cid, "user", "pergunta que falhou")
        conv.add_message(cid, "assistant", "Não consegui responder…", None, "error")
        conv.add_message(cid, "user", "pergunta boa")
        conv.add_message(cid, "assistant", "10 €", "SELECT 1", "sql")
        assert conv.get_history(cid) == [("pergunta boa", "SELECT 1")]
    finally:
        conv.delete_conversation("gerente.maia", cid)


def test_migration_marks_old_error_answers():
    """V004__conversations.sql corrige respostas com erro gravadas pela versão anterior."""
    cid = conv.create_conversation("gerente.maia", "migração")
    try:
        conv.add_message(cid, "assistant", "Não consegui responder a essa pergunta.", "SELECT partido", None)
        with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as c:
            c.execute((ROOT / "db" / "migrations" / "V004__conversations.sql").read_text(encoding="utf-8"))
            kind, sql = c.execute("SELECT kind, sql FROM messages WHERE conversation_id = %s", (cid,)).fetchone()
        assert (kind, sql) == ("error", None)
    finally:
        conv.delete_conversation("gerente.maia", cid)


# ---------- 2. Dados e previsão acompanham a data de hoje ----------

def test_data_goes_until_yesterday_or_extend_catches_up():
    with psycopg.connect(os.environ["DATABASE_URL"]) as c, c.cursor() as cur:
        last = generate_activity.last_sale_day(cur)
        if last < generate_activity.yesterday():
            pytest.skip(f"Dados até {last}: corre generate_activity --extend")
        assert generate_activity.extend(cur) == 0     # já em dia: não faz nada
        c.rollback()


@pytest.mark.model
def test_forecast_starts_today_even_with_stale_data():
    from multistore_ai_assistant.forecast.predict import forecast
    later = date.today() + timedelta(days=12)        # simula 12 dias sem novos dados
    df = forecast(7, today=later)
    assert df["day"].min().date() == later and df["day"].nunique() == 7


# ---------- 3. Catálogo por marca ----------

@pytest.mark.parametrize("table", ["products", "menus", "product_margins", "menu_margins", "price_recommendations"])
def test_brand_manager_sees_only_own_catalog(brands, table):
    for brand_id in brands:
        seen = {r[0] for r in run_query(f"SELECT DISTINCT brand_id FROM {table}", marca(brand_id))[1]}
        assert seen <= {brand_id}, (table, brand_id, seen)
    all_brands = {r[0] for r in run_query(f"SELECT DISTINCT brand_id FROM {table}", IMPERADOR)[1]}
    assert len(all_brands) >= 2


def test_store_manager_sees_only_own_brand_catalog():
    with psycopg.connect(os.environ["DATABASE_URL"]) as c:
        store_id, brand_id = c.execute("SELECT id, brand_id FROM stores ORDER BY id LIMIT 1").fetchone()
    loja = {"role": "loja", "brand_id": None, "store_id": store_id}
    assert {r[0] for r in run_query("SELECT DISTINCT brand_id FROM products", loja)[1]} == {brand_id}


def test_recipes_and_menu_items_follow_the_brand(brands):
    first = next(iter(brands))
    other = run_query(f"""SELECT count(*) FROM recipes r JOIN products p ON p.id = r.product_id
                          WHERE p.brand_id <> {first}""", IMPERADOR)[1][0][0]
    assert other > 0
    assert run_query("SELECT count(*) FROM recipes", marca(first))[1][0][0] \
        == run_query(f"SELECT count(*) FROM recipes r JOIN products p ON p.id = r.product_id WHERE p.brand_id = {first}",
                     IMPERADOR)[1][0][0]
    # sem passar pelo JOIN: a política de recipes/menu_items filtra sozinha
    assert run_query("SELECT count(*) FROM menu_items", marca(first))[1][0][0] \
        < run_query("SELECT count(*) FROM menu_items", IMPERADOR)[1][0][0]


# ---------- 4. run_query exige o utilizador ----------

@pytest.mark.parametrize("user", [None, {}, {"brand_id": 1}])
def test_run_query_requires_a_user(user):
    with pytest.raises(ValueError):
        run_query("SELECT count(*) FROM sales", user)


# ---------- 5. R__readonly.sql sozinho não abre nada ----------

def test_readonly_sql_alone_keeps_private_data_closed():
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as c:
        c.execute((ROOT / "db" / "migrations" / "R__readonly.sql").read_text(encoding="utf-8"))
        assert c.execute("SELECT count(*) FROM pg_default_acl").fetchone()[0] == 0
        has_setup = c.execute("SELECT to_regclass('public.setup_steps') IS NOT NULL").fetchone()[0]
    private = ["SELECT key FROM app_secret", "SELECT password_hash FROM users",
               "SELECT nif FROM employees", "SELECT * FROM conversations"]
    if has_setup:                      # criada pelo entrypoint do Docker
        private.append("SELECT * FROM setup_steps")
    for sql in private:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            run_query(sql, IMPERADOR)


def test_new_tables_are_not_readable_by_default():
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as c:
        c.execute("CREATE TABLE IF NOT EXISTS pytest_nova (x int)")
        try:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                run_query("SELECT * FROM pytest_nova", IMPERADOR)
        finally:
            c.execute("DROP TABLE pytest_nova")
