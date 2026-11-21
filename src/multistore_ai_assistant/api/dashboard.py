"""KPIs do painel de vendas: faturação, top lojas, margem por marca e previsão.

Todas as consultas passam por ``run_query`` (RLS + assinatura HMAC), por isso
cada perfil só vê o seu grupo / marca / loja. Cada secção exige o módulo
correspondente, como no chat: ``sql`` para os números de vendas, ``forecast``
para a previsão (que reutiliza a previsão do dia, em cache).

Os limites de datas são ``timestamp`` (``localtimestamp``), como a coluna
``sold_at``: comparar com ``timestamptz``/``date`` usa operadores não-leakproof,
que com RLS dão planos lentos (ver ``sql_validator.TIMESTAMP_COLUMNS``).
"""
from multistore_ai_assistant.api.errors import ApiError
from multistore_ai_assistant.api.features import has_feature
from multistore_ai_assistant.api.permissions import has_module
from multistore_ai_assistant.db.query import run_query
from multistore_ai_assistant.forecast.service import forecast_answer

# Mês corrente até agora vs. o mesmo tempo decorrido no mês passado (sem passar do fim
# dele: a 31 de março compara com fevereiro inteiro). "days" = dia do mês de hoje.
REVENUE_SQL = """
WITH p AS (
  SELECT date_trunc('month', localtimestamp) AS m0,
         localtimestamp AS now_ts,
         date_trunc('month', localtimestamp) - interval '1 month' AS l0,
         least(date_trunc('month', localtimestamp) - interval '1 month'
                 + (localtimestamp - date_trunc('month', localtimestamp)),
               date_trunc('month', localtimestamp)) AS l_end
)
SELECT round(coalesce(sum(s.total) FILTER (WHERE s.sold_at >= p.m0 AND s.sold_at < p.now_ts), 0), 2),
       round(coalesce(sum(s.total) FILTER (WHERE s.sold_at >= p.l0 AND s.sold_at < p.l_end), 0), 2),
       extract(day FROM p.now_ts)::int
FROM p
LEFT JOIN sales s ON s.sold_at >= p.l0 AND s.sold_at < p.now_ts
GROUP BY p.m0, p.now_ts, p.l0, p.l_end
"""

TOP_STORES_SQL = """
SELECT st.name AS store,
       round(sum(s.total), 2) AS revenue
FROM sales s
JOIN stores st ON st.id = s.store_id
WHERE s.sold_at >= date_trunc('month', localtimestamp)
  AND s.sold_at < date_trunc('month', localtimestamp) + interval '1 month'
GROUP BY st.name
ORDER BY revenue DESC
LIMIT 5
"""

# Custo só "conhecido" se o produto tem receita (e todos os ingredientes têm custo) ou se o
# menu tem produtos e todos são conhecidos. As views product_margins / menu_margins tratam
# custo em falta como 0 (margem inflacionada): aqui essas vendas ficam de fora e são contadas.
MARGIN_BY_BRAND_SQL = """
WITH product_cost AS (
  SELECT p.id AS product_id,
         round(sum(r.quantity * i.unit_cost), 2) AS unit_cost,
         count(r.product_id) > 0 AND coalesce(bool_and(i.unit_cost IS NOT NULL), false) AS known
  FROM products p
  LEFT JOIN recipes r ON r.product_id = p.id
  LEFT JOIN ingredients i ON i.id = r.ingredient_id
  GROUP BY p.id
), menu_cost AS (
  SELECT m.id AS menu_id,
         round(sum(mi.quantity * pc.unit_cost), 2) AS unit_cost,
         count(mi.menu_id) > 0 AND coalesce(bool_and(pc.known), false) AS known
  FROM menus m
  LEFT JOIN menu_items mi ON mi.menu_id = m.id
  LEFT JOIN product_cost pc ON pc.product_id = mi.product_id
  GROUP BY m.id
), line AS (
  SELECT b.name AS brand, sl.quantity, sl.unit_price,
         CASE WHEN sl.product_id IS NOT NULL THEN pc.unit_cost ELSE mc.unit_cost END AS unit_cost,
         coalesce(CASE WHEN sl.product_id IS NOT NULL THEN pc.known ELSE mc.known END, false) AS known,
         CASE WHEN sl.product_id IS NOT NULL THEN 'p' || sl.product_id ELSE 'm' || sl.menu_id END AS item
  FROM sale_lines sl
  JOIN sales s ON s.id = sl.sale_id
  JOIN stores st ON st.id = s.store_id
  JOIN brands b ON b.id = st.brand_id
  LEFT JOIN product_cost pc ON pc.product_id = sl.product_id
  LEFT JOIN menu_cost mc ON mc.menu_id = sl.menu_id
  WHERE s.sold_at >= date_trunc('month', localtimestamp)
    AND s.sold_at < date_trunc('month', localtimestamp) + interval '1 month'
)
SELECT brand,
       round(sum(quantity * (unit_price - unit_cost)) FILTER (WHERE known), 2) AS margin,
       count(DISTINCT item) FILTER (WHERE NOT known) AS excluded_items
FROM line
GROUP BY brand
ORDER BY margin DESC NULLS LAST
"""


def _pair(columns: list[str], rows: list[tuple]) -> list[dict]:
    return [dict(zip(columns, row, strict=True)) for row in rows]


def _num(value) -> float:
    return round(float(value or 0), 2)


def _sales_sections(user: dict) -> dict:
    """Faturação (mês até hoje vs. mesmos dias do mês passado), top lojas e margem por marca."""
    _, rev_rows = run_query(REVENUE_SQL, user)
    this_month, last_month, days = rev_rows[0] if rev_rows else (0, 0, None)
    this_month, last_month = _num(this_month), _num(last_month)
    change_pct = round(100 * (this_month - last_month) / last_month, 1) if last_month else None

    top_cols, top_rows = run_query(TOP_STORES_SQL, user)
    margin_cols, margin_rows = run_query(MARGIN_BY_BRAND_SQL, user)
    margins = [{**m, "margin": None if m["margin"] is None else _num(m["margin"]),
                "excluded_items": int(m["excluded_items"])}
               for m in _pair(margin_cols, margin_rows)]
    return {
        "revenue": {"this_month_to_date": this_month, "last_month_same_days": last_month,
                    "days": days, "change_pct": change_pct},
        "top_stores": _pair(top_cols, top_rows),
        "margin_by_brand": margins,
        "margin_excluded_items": sum(m["excluded_items"] for m in margins),
    }


def dashboard_for(user: dict) -> dict:
    """KPIs do âmbito do utilizador (RLS), só das secções cujos módulos a conta tem.

    Returns:
        Com ``sql``: ``revenue``, ``top_stores``, ``margin_by_brand``, ``margin_excluded_items``.
        Com ``forecast``: ``forecast_7d`` (colunas + linhas diárias).

    Raises:
        ApiError 403 (``no_module``): a conta não tem nenhum dos dois módulos.
    """
    out: dict = {}
    if has_module(user, "sql") and has_feature(user, "chat"):
        out.update(_sales_sections(user))
    if has_module(user, "forecast") and has_feature(user, "forecast"):
        fc_cols, fc_rows = forecast_answer(user, days=7)
        out["forecast_7d"] = {"columns": fc_cols, "rows": [list(r) for r in fc_rows]}
    if not out:
        raise ApiError("no_module", 403, module="sql")
    return out
