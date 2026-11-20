"""GET /dashboard: módulos, formato da resposta e cache da previsão (BD simulada).

O RLS e os números reais (mês até hoje, margens) estão em tests/integration/test_dashboard_db.py.
"""
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from multistore_ai_assistant.api import auth
from multistore_ai_assistant.api import dashboard as dash_mod
from multistore_ai_assistant.api import main as api
from multistore_ai_assistant.forecast import service
from tests.conftest import IMPERADOR, LOJA, MARCA

client = TestClient(api.app)
FORECAST = (["day", "forecast_revenue_eur"], [("2026-11-21", 50.0)])


def bearer(user=LOJA) -> dict:
    return {"Authorization": "Bearer " + auth.create_token(user)}


@pytest.fixture
def db(monkeypatch):
    """BD e previsão simuladas; ``calls`` diz o que correu."""
    calls = {"sql": [], "forecast": 0}

    def fake_run(sql, user):
        calls["sql"].append(sql)
        if "last_month" in sql or "l_end" in sql:
            return ["a", "b", "c"], [(1500.0, 1000.0, 20)]
        if "LIMIT 5" in sql:
            return ["store", "revenue"], [("BurgerLab Maia", 400.0)]
        return ["brand", "margin", "excluded_items"], [("BurgerLab", 90.0, 2), ("Café Aroma", None, 1)]

    def fake_forecast(user, days=7):
        calls["forecast"] += 1
        return FORECAST
    monkeypatch.setattr(dash_mod, "run_query", fake_run)
    monkeypatch.setattr(dash_mod, "forecast_answer", fake_forecast)
    return calls


def with_modules(fake_users, user, modules):
    fake_users[user["username"]] = {**user, "modules": modules}
    return fake_users[user["username"]]


def test_dashboard_requires_login():
    assert client.get("/dashboard").status_code in (401, 403)


@pytest.mark.parametrize("user", [LOJA, MARCA, IMPERADOR])
def test_full_dashboard_for_accounts_with_both_modules(db, user):
    body = client.get("/dashboard", headers=bearer(user)).json()
    assert set(body) == {"revenue", "top_stores", "margin_by_brand", "margin_excluded_items", "forecast_7d"}


def test_payload(db):
    body = dash_mod.dashboard_for(LOJA)
    assert body["revenue"] == {"this_month_to_date": 1500.0, "last_month_same_days": 1000.0,
                               "days": 20, "change_pct": 50.0}
    assert body["top_stores"] == [{"store": "BurgerLab Maia", "revenue": 400.0}]
    assert body["margin_by_brand"] == [{"brand": "BurgerLab", "margin": 90.0, "excluded_items": 2},
                                       {"brand": "Café Aroma", "margin": None, "excluded_items": 1}]
    assert body["margin_excluded_items"] == 3                   # a UI diz quantos ficaram de fora
    assert body["forecast_7d"] == {"columns": FORECAST[0], "rows": [["2026-11-21", 50.0]]}


def test_change_pct_is_none_without_last_month(db, monkeypatch):
    monkeypatch.setattr(dash_mod, "run_query", lambda sql, user: (["a", "b", "c"], [(10.0, 0.0, 3)])
                        if "l_end" in sql else (["x"], []))
    assert dash_mod.dashboard_for(LOJA)["revenue"]["change_pct"] is None


# ---------- módulos ----------

def test_without_sql_only_the_forecast_and_no_query_runs(db, fake_users):
    user = with_modules(fake_users, LOJA, ["forecast"])
    r = client.get("/dashboard", headers=bearer(user))
    assert r.status_code == 200 and set(r.json()) == {"forecast_7d"}
    assert db["sql"] == []                                      # nem a faturação nem as margens correram


def test_without_forecast_no_forecast_and_the_model_does_not_run(db, fake_users):
    user = with_modules(fake_users, LOJA, ["sql", "orders"])
    body = client.get("/dashboard", headers=bearer(user)).json()
    assert "forecast_7d" not in body and "revenue" in body and db["forecast"] == 0


def test_without_either_module_it_is_403(db, fake_users):
    user = with_modules(fake_users, LOJA, ["orders"])
    r = client.get("/dashboard", headers={**bearer(user), "Accept-Language": "en"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "no_module"
    assert db == {"sql": [], "forecast": 0}


def test_demo_accounts_can_open_it(db, fake_users):
    demo = {**IMPERADOR, "protected": True}
    fake_users["pedro"] = demo
    assert client.get("/dashboard", headers=bearer(demo)).status_code == 200


# ---------- previsão em cache por dia ----------

def test_the_forecast_model_runs_once_per_day(monkeypatch):
    runs = []
    frame = pd.DataFrame({"store_id": [1, 2], "day": pd.to_datetime(["2026-11-21"] * 2), "revenue": [10.0, 20.0]})
    monkeypatch.setattr(service, "forecast", lambda days: runs.append(days) or frame)
    monkeypatch.setattr(service, "visible_stores", lambda u: [1] if u is LOJA else [1, 2])
    assert service.forecast_answer(LOJA)[1] == [("2026-11-21", 10.0)]
    assert service.forecast_answer(IMPERADOR)[1] == [("2026-11-21", 30.0)]   # o filtro RLS continua por pedido
    assert runs == [7]

    class Tomorrow(service.date):
        @classmethod
        def today(cls):
            return service.date(2099, 1, 2)
    monkeypatch.setattr(service, "date", Tomorrow)
    service.forecast_answer(LOJA)
    assert runs == [7, 7]                                       # dia novo: corre outra vez


def test_cached_forecast_is_not_mutated_by_callers(monkeypatch):
    frame = pd.DataFrame({"store_id": [1], "day": pd.to_datetime(["2026-11-21"]), "revenue": [10.0]})
    monkeypatch.setattr(service, "forecast", lambda days: frame)
    mine = service.daily_forecast(7)
    mine["revenue"] = 0.0                                       # um caller a mexer no que recebeu…
    assert service.daily_forecast(7)["revenue"].tolist() == [10.0]   # …não estraga a cache
