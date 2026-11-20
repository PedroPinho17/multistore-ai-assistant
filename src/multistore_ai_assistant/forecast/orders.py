"""Sugere encomendas de ingredientes a partir da previsão de faturação.

Combina: (uso de ingrediente por euro nos últimos 28 dias) × (receita prevista)
− stock actual → quantidade a encomendar (mínimo 0).

``to_order`` em unidades de contagem (``un``, ``unidades``) arredonda para cima ao
inteiro (não se encomenda meia unidade); peso/volume (kg, l, …) fica com 2 casas.
``needed`` é a estimativa de consumo (2 casas, nunca arredondada para cima): os
alertas de stock calculam os dias de cobertura a partir dela.
"""
import math
import sys

import pandas as pd
from dotenv import load_dotenv

from multistore_ai_assistant.db.pool import connection

from .predict import forecast

load_dotenv()

# Unidades de contagem: não se encomenda meia unidade
COUNT_UNITS = frozenset({"un", "unidade", "unidades", "u", "unit", "units"})


def round_order_qty(value: float, unit: str) -> float:
    """Quantidade a encomendar: contagem → ``ceil``; resto → 2 decimais.

    O ``round(…, 6)`` antes do ``ceil`` tira o ruído de vírgula flutuante
    (``3.0000000000000004`` é 3, não 4).
    """
    qty = float(value)
    if str(unit).strip().lower() in COUNT_UNITS:
        return float(math.ceil(round(qty, 6)))
    return round(qty, 2)

# Uso de ingredientes por euro de faturação (28 dias) + stock actual por loja
USAGE_QUERY = """
WITH linhas AS (
  SELECT s.store_id, sl.product_id, sl.quantity
  FROM sale_lines sl JOIN sales s ON s.id = sl.sale_id
  WHERE s.sold_at >= current_date - INTERVAL '28 days' AND sl.product_id IS NOT NULL
  UNION ALL
  SELECT s.store_id, mi.product_id, sl.quantity * mi.quantity
  FROM sale_lines sl JOIN sales s ON s.id = sl.sale_id
  JOIN menu_items mi ON mi.menu_id = sl.menu_id
  WHERE s.sold_at >= current_date - INTERVAL '28 days'
),
uso AS (
  SELECT l.store_id, r.ingredient_id, sum(l.quantity * r.quantity) AS used
  FROM linhas l JOIN recipes r ON r.product_id = l.product_id
  GROUP BY l.store_id, r.ingredient_id
),
fat AS (
  SELECT store_id, sum(total) AS revenue
  FROM sales WHERE sold_at >= current_date - INTERVAL '28 days'
  GROUP BY store_id
)
SELECT u.store_id, i.id AS ingredient_id, i.name AS ingredient, i.unit,
       u.used / f.revenue AS per_euro,
       coalesce(st.quantity, 0) AS stock
FROM uso u
JOIN fat f ON f.store_id = u.store_id
JOIN ingredients i ON i.id = u.ingredient_id
LEFT JOIN stock st ON st.store_id = u.store_id AND st.ingredient_id = u.ingredient_id
"""


def suggest_orders(store_id: int | None = None, days: int = 7) -> pd.DataFrame:
    """Calcula ingredientes a encomendar para o horizonte ``days``.

    Args:
        store_id: Filtra a previsão a uma loja; ``None`` = todas.
        days: Dias de previsão de faturação.

    Returns:
        DataFrame com ``store_id``, ``ingredient``, ``unit``, ``needed``,
        ``stock``, ``to_order``.
    """
    with connection("owner") as conn:
        cur = conn.execute(USAGE_QUERY)
        usage = pd.DataFrame(cur.fetchall(), columns=[c.name for c in cur.description])
    for col in ["per_euro", "stock"]:
        usage[col] = usage[col].astype(float)

    fc = forecast(days, store_id).groupby("store_id", as_index=False)["revenue"].sum()
    df = usage.merge(fc, on="store_id")
    needed = df["per_euro"] * df["revenue"]
    df["needed"] = needed.round(2)                      # estimativa: nunca arredondada para cima
    missing = (needed - df["stock"]).clip(lower=0)
    df["to_order"] = [round_order_qty(v, u) for v, u in zip(missing, df["unit"], strict=True)]
    return (
        df[["store_id", "ingredient", "unit", "needed", "stock", "to_order"]]
        .sort_values(["store_id", "to_order"], ascending=[True, False])
    )


if __name__ == "__main__":
    store = int(sys.argv[1]) if len(sys.argv) > 1 else None
    print(suggest_orders(store).to_string(index=False))
