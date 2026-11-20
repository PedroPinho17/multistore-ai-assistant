"""Fachada do forecast para o assistente: respeita o RLS do utilizador.

Filtra as previsões / encomendas às lojas que o perfil consegue ver
(``SELECT id FROM stores`` já passa pelo RLS).
"""
import threading
from datetime import date

from ..db.query import run_query
from .orders import round_order_qty, suggest_orders
from .predict import forecast

# Previsão de TODAS as lojas, por (dia, horizonte): o modelo só corre uma vez por dia
# (~0,6 s). O filtro por lojas visíveis (RLS) é feito depois, em cada pedido.
_forecast_cache: dict[tuple[date, int], object] = {}
_forecast_lock = threading.Lock()


def daily_forecast(days: int = 7):
    """``forecast(days)`` de todas as lojas, guardada até mudar o dia."""
    key = (date.today(), days)
    with _forecast_lock:
        if key not in _forecast_cache:
            _forecast_cache.clear()                  # só o dia de hoje interessa
            _forecast_cache[key] = forecast(days)
        return _forecast_cache[key].copy()


def clear_forecast_cache() -> None:
    """Esquece a previsão guardada (p.ex. depois de treinar o modelo de novo; usado nos testes)."""
    with _forecast_lock:
        _forecast_cache.clear()


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
    df = daily_forecast(days)
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
