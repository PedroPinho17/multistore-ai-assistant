"""GET /dashboard na BD real: RLS por perfil, mês até hoje, margens e módulos.

As asserções de âmbito são exatas (a loja vê só a BurgerLab Maia), não só "≤": com
"≤" um RLS partido que mostrasse o grupo inteiro à loja também passava.
"""
import os
from datetime import timedelta
from decimal import Decimal

import psycopg
import pytest
from fastapi.testclient import TestClient

from multistore_ai_assistant.api import auth
from multistore_ai_assistant.api import main as api
from multistore_ai_assistant.api.auth import load_user
from multistore_ai_assistant.api.dashboard import dashboard_for

pytestmark = pytest.mark.integration

try:
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=3) as _c:
        _ok = _c.execute("SELECT to_regclass('public.sales') IS NOT NULL").fetchone()[0]
except Exception:
    _ok = False
if not _ok:
    pytest.skip("Base de dados indisponível", allow_module_level=True)

client = TestClient(api.app)


def owner():
    return psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)


def user(username: str) -> dict:
    found = load_user(username)
    assert found, f"conta de demo {username} em falta"
    return found


def bearer(username: str) -> dict:
    return {"Authorization": "Bearer " + auth.create_token(user(username))}


@pytest.fixture(scope="module")
def boards():
    """O painel de cada perfil (calcula-se uma vez: a previsão e as queries custam)."""
    return {name: dashboard_for(user(name)) for name in ("gerente.maia", "gestor.burgerlab", "pedro")}


# ---------- RLS ----------

def test_store_manager_sees_only_their_store(boards):
    loja = boards["gerente.maia"]
    assert [s["store"] for s in loja["top_stores"]] == ["BurgerLab Maia"]
    assert [m["brand"] for m in loja["margin_by_brand"]] == ["BurgerLab"]


def test_brand_manager_sees_only_their_brand(boards):
    marca = boards["gestor.burgerlab"]
    assert marca["top_stores"] and all(s["store"].startswith("BurgerLab ") for s in marca["top_stores"])
    assert [m["brand"] for m in marca["margin_by_brand"]] == ["BurgerLab"]


def test_scopes_are_strictly_nested(boards):
    loja, marca, grupo = (boards[n] for n in ("gerente.maia", "gestor.burgerlab", "pedro"))
    assert 0 < loja["revenue"]["this_month_to_date"] < marca["revenue"]["this_month_to_date"] \
        < grupo["revenue"]["this_month_to_date"]
    assert {m["brand"] for m in grupo["margin_by_brand"]} == {"BurgerLab", "Café Aroma", "Gelato Mar"}
    loja_margin = loja["margin_by_brand"][0]["margin"]
    assert loja_margin < marca["margin_by_brand"][0]["margin"]


def test_the_store_numbers_are_exactly_that_stores(boards):
    """A faturação da loja é a da BurgerLab Maia (calculada sem RLS, com a conta dona)."""
    with owner() as c:
        now = c.execute("SELECT localtimestamp").fetchone()[0]
        m0 = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        mine = c.execute("SELECT coalesce(sum(total), 0) FROM sales WHERE store_id = 1 AND sold_at >= %s AND sold_at < %s",
                         (m0, now)).fetchone()[0]
    assert Decimal(str(boards["gerente.maia"]["revenue"]["this_month_to_date"])) == round(mine, 2)


# ---------- mês até hoje vs. os mesmos dias do mês passado ----------

def test_month_to_date_compares_the_same_days_of_last_month(boards):
    with owner() as c:
        now = c.execute("SELECT localtimestamp").fetchone()[0]
        m0 = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        l0 = (m0 - timedelta(days=1)).replace(day=1)
        l_end = min(l0 + (now - m0), m0)                     # sem passar do fim do mês passado
        this, last = c.execute(
            "SELECT coalesce(sum(total) FILTER (WHERE sold_at >= %(m0)s AND sold_at < %(now)s), 0),"
            "       coalesce(sum(total) FILTER (WHERE sold_at >= %(l0)s AND sold_at < %(l_end)s), 0) FROM sales",
            {"m0": m0, "now": now, "l0": l0, "l_end": l_end}).fetchone()
    revenue = boards["pedro"]["revenue"]
    assert revenue["days"] == now.day
    assert Decimal(str(revenue["this_month_to_date"])) == round(this, 2)
    assert Decimal(str(revenue["last_month_same_days"])) == round(last, 2)
    assert revenue["change_pct"] == round(100 * float(this - last) / float(last), 1)


# ---------- margem: produtos sem custo ficam de fora (e são contados) ----------

@pytest.fixture
def product_without_cost():
    """Um produto sem receita, vendido agora na BurgerLab Maia; apagado no fim."""
    with owner() as c:
        pid = c.execute("INSERT INTO products (brand_id, name, category, price) "
                        "VALUES (1, 'pytest sem receita', 'teste', 1000) RETURNING id").fetchone()[0]
        sid = c.execute("INSERT INTO sales (store_id, sold_at, payment_method, total) "
                        "VALUES (1, localtimestamp - interval '1 minute', 'dinheiro', 3000) RETURNING id").fetchone()[0]
        c.execute("INSERT INTO sale_lines (sale_id, product_id, quantity, unit_price) VALUES (%s, %s, 3, 1000)",
                  (sid, pid))
    try:
        yield
    finally:
        with owner() as c:
            c.execute("DELETE FROM sale_lines WHERE sale_id = %s", (sid,))
            c.execute("DELETE FROM sales WHERE id = %s", (sid,))
            c.execute("DELETE FROM products WHERE id = %s", (pid,))


def test_products_without_cost_are_excluded_from_the_margin_and_counted(boards, product_without_cost):
    before = boards["gerente.maia"]["margin_by_brand"][0]
    after = dashboard_for(user("gerente.maia"))
    burgerlab = after["margin_by_brand"][0]
    # Com custo 0 (como antes), a margem subia 3 × 1000 €; agora fica igual e o produto é contado
    assert burgerlab["margin"] == before["margin"]
    assert burgerlab["excluded_items"] == before["excluded_items"] + 1
    assert after["margin_excluded_items"] == boards["gerente.maia"]["margin_excluded_items"] + 1


# ---------- módulos e HTTP ----------

def test_http_dashboard_for_store_manager():
    r = client.get("/dashboard", headers=bearer("gerente.maia"))
    assert r.status_code == 200
    assert set(r.json()) == {"revenue", "top_stores", "margin_by_brand", "margin_excluded_items", "forecast_7d"}


def test_modules_are_enforced_against_the_real_database(monkeypatch):
    real = load_user

    def with_modules(modules):
        def load(name):
            found = real(name)
            return found and {**found, "modules": modules}
        monkeypatch.setattr(auth, "load_user", load)

    with_modules(["forecast"])
    assert set(client.get("/dashboard", headers=bearer("gerente.maia")).json()) == {"forecast_7d"}
    with_modules(["sql"])
    assert "forecast_7d" not in client.get("/dashboard", headers=bearer("gerente.maia")).json()
    with_modules(["orders"])
    assert client.get("/dashboard", headers=bearer("gerente.maia")).status_code == 403


def test_demo_imperador_can_open_dashboard():
    assert client.get("/dashboard", headers=bearer("pedro")).status_code == 200
