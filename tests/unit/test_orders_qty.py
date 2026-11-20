"""Arredondamento nas sugestões de encomenda e o seu efeito nos alertas de stock.

``suggest_orders`` e ``stock_alerts`` correm a sério: só a BD (o consumo por euro e o
stock) e o modelo de previsão (a faturação) são simulados.
"""
from decimal import Decimal

import pandas as pd
import pytest

from multistore_ai_assistant.api import alerts
from multistore_ai_assistant.forecast import orders
from multistore_ai_assistant.forecast.orders import round_order_qty, suggest_orders
from tests.conftest import IMPERADOR


@pytest.mark.parametrize("value,unit,expected", [
    (10.01, "un", 11.0),
    (10.0, "un", 10.0),
    (0.1, "unidades", 1.0),
    (0.0, "un", 0.0),
    (2.3, "UN", 3.0),
    (2.3, " unidade ", 3.0),
    (1.234, "kg", 1.23),
    (1.235, "kg", 1.24),
    (0.456, "l", 0.46),
    (0.1, "L", 0.1),
])
def test_round_order_qty_by_unit(value, unit, expected):
    assert round_order_qty(value, unit) == expected


@pytest.mark.parametrize("value,expected", [
    ((0.1 + 0.2) * 10, 3.0),          # 3.0000000000000004: ruído, não é mais um
    (2.9999999999999996, 3.0),
    (3.000002, 4.0),                  # acima do ruído: conta como mais uma unidade
])
def test_float_noise_does_not_order_an_extra_unit(value, expected):
    assert round_order_qty(value, "un") == expected


# ---------- suggest_orders e stock_alerts com o cálculo real ----------

USAGE_COLUMNS = ["store_id", "ingredient_id", "ingredient", "unit", "per_euro", "stock"]
# A BD devolve numeric → Decimal (como o psycopg). Faturação prevista: loja 1 = 1000 €, loja 2 = 10 €.
USAGE = [
    (1, 1, "Pão", "un", Decimal("0.0102"), Decimal("0.75")),          # 10,2 un; cobre 0,51 dias
    (1, 2, "Copos", "un", Decimal("0.012"), Decimal("0")),            # 12 un certinhas
    (1, 3, "Alface", "kg", Decimal("0.001234"), Decimal("0.1")),      # 1,234 kg
    (1, 4, "Guardanapos", "un", Decimal("0.0003"), Decimal("0.02")),  # 0,3 un/semana; cobre 0,47 dias
    (2, 5, "Molho", "un", Decimal(0.1 + 0.2), Decimal("0")),          # 3.0000000000000004 un
]


class FakeCursor:
    description = [type("Col", (), {"name": c}) for c in USAGE_COLUMNS]

    def fetchall(self):
        return list(USAGE)


class FakeConn:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        return FakeCursor()


@pytest.fixture
def orders_data(monkeypatch):
    monkeypatch.setattr(orders, "connection", lambda kind="owner": FakeConn())
    monkeypatch.setattr(orders, "forecast", lambda days, store_id=None: pd.DataFrame(
        {"store_id": [1, 1, 2], "revenue": [400.0, 600.0, 10.0]}))
    monkeypatch.setattr(alerts, "run_query", lambda sql, user: (["id", "name"], [(1, "Loja A"), (2, "Loja B")]))


def test_suggest_orders_rounds_only_what_to_order(orders_data):
    df = suggest_orders(None, 7).set_index("ingredient")
    #                  needed (estimativa)  to_order
    assert (df.loc["Pão", "needed"], df.loc["Pão", "to_order"]) == (10.2, 10.0)        # 9,45 → 10
    assert (df.loc["Copos", "needed"], df.loc["Copos", "to_order"]) == (12.0, 12.0)    # inteiro fica igual
    assert (df.loc["Alface", "needed"], df.loc["Alface", "to_order"]) == (1.23, 1.13)  # kg: 2 casas
    assert (df.loc["Guardanapos", "needed"], df.loc["Guardanapos", "to_order"]) == (0.3, 1.0)
    assert (df.loc["Molho", "needed"], df.loc["Molho", "to_order"]) == (3.0, 3.0)      # ruído: 3, não 4


def test_stock_alerts_use_the_real_consumption_of_un_items(orders_data):
    """Com ``needed`` arredondado para cima, o Pão (0,51 dias) passava a alerta e os
    Guardanapos (0,47 dias, «warn») passavam a «high» (1 un em vez de 0,3 por semana)."""
    items = {a["ingredient"]: a for a in alerts.stock_alerts(IMPERADOR)}
    # Copos e Molho estão a zero (alerta certo); Alface cobre 0,57 dias; o Pão não pode aparecer
    assert {k: a["severity"] for k, a in items.items()} == {"Copos": "high", "Molho": "high", "Guardanapos": "warn"}
    assert items["Guardanapos"]["days"] == round(0.02 / (0.3 / 7), 1)
