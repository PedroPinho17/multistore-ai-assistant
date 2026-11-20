"""Fachada do forecast para o assistente: respeita o RLS do utilizador.

Filtra as previsões / encomendas às lojas que o perfil consegue ver
(``SELECT id FROM stores`` já passa pelo RLS).
"""
from ..db.query import run_query
from .orders import round_order_qty, suggest_orders
from .predict import forecast


def visible_stores(user: dict | None) -> list[int]:
    """Ids das lojas visíveis para o perfil (Imperador = todas)."""
    _, rows = run_query("SELECT id FROM stores ORDER BY id", user)
    return [r[0] for r in rows]


def forecast_answer(user: dict | None, days: int = 7):
    """Previsão de faturação diária agregada (lojas visíveis).

    Returns:
        ``(colunas, linhas)`` prontas para a UI / ``answer()``.
    """
    stores = visible_stores(user)
    df = forecast(days)
    df = df[df["store_id"].isin(stores)]
    daily = df.groupby("day", as_index=False)["revenue"].sum()
    columns = ["day", "forecast_revenue_eur"]
    rows = [
        (d.strftime("%Y-%m-%d"), round(v, 2))
        for d, v in zip(daily["day"], daily["revenue"], strict=False)
    ]
    return columns, rows


def orders_answer(user: dict | None, days: int = 7):
    """Sugestão de encomenda de ingredientes para as lojas visíveis.

    Agrega ``needed`` / ``stock`` / ``to_order`` por ingrediente.

    Returns:
        ``(colunas, linhas)`` ordenadas por quantidade a encomendar (desc).
    """
    stores = visible_stores(user)
    df = suggest_orders(None, days)
    df = df[df["store_id"].isin(stores)]
    agg = df.groupby(["ingredient", "unit"], as_index=False)[["needed", "stock", "to_order"]].sum()
    agg = agg.sort_values("to_order", ascending=False)
    columns = ["ingredient", "unit", "needed_7_days", "stock", "to_order"]
    rows = []
    for ingredient, unit, needed, stock, to_order in agg.itertuples(index=False):
        rows.append((
            ingredient,
            unit,
            round(float(needed), 2),            # estimativa de consumo
            round(float(stock), 2),
            round_order_qty(to_order, unit),
        ))
    return columns, rows
