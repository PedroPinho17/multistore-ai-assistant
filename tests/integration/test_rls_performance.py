"""Desempenho sob RLS (precisa do Postgres com os dados: docker compose up -d).

Com RLS ativo, o Postgres só usa as estatísticas de uma coluna em operadores
``LEAKPROOF``. ``timestamp >= date`` não é: o planeador estimava 1 linha em vez de
~380 000 e as perguntas 16 e 27 do eval passavam os 10 s do statement_timeout
(0,3 s sem RLS). O validador passa as comparações com colunas ``timestamp`` para
``timestamp`` (ver ``TIMESTAMP_COLUMNS`` em sql_validator); estes testes medem isso
na BD real, com os três perfis.
"""
import json
import os
import time

import psycopg
import pytest

from multistore_ai_assistant.assistant.sql_validator import TIMESTAMP_COLUMNS, validate_sql
from multistore_ai_assistant.db.query import run_query
from tests.conftest import IMPERADOR

pytestmark = pytest.mark.integration

MAX_SECONDS = 3.0     # sem a correção: > 10 s (statement_timeout); com ela: ~0,3 s


def _db_with_sales() -> bool:
    try:
        with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=3) as conn:
            return conn.execute("SELECT count(*) > 100000 FROM sales").fetchone()[0]
    except Exception:
        return False


if not _db_with_sales():
    pytest.skip("Base de dados indisponível ou sem dados de vendas", allow_module_level=True)


@pytest.fixture(scope="module")
def users():
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        rows = conn.execute("SELECT username, role, brand_id, store_id FROM users "
                            "WHERE username IN ('pedro', 'gestor.burgerlab', 'gerente.maia')").fetchall()
    return {u: {"username": u, "role": r, "brand_id": b, "store_id": s} for u, r, b, s in rows}


# SQL tal como o LLM o escreveu no eval de 20/11/2026 (datas como CAST(... AS DATE))
Q27 = ("SELECT b.name AS marca, ROUND(100.0 * SUM(s.total) / t.total_revenue, 2) AS participacao_percentual "
       "FROM sales AS s JOIN stores AS st ON st.id = s.store_id JOIN brands AS b ON b.id = st.brand_id "
       "CROSS JOIN (SELECT SUM(total) AS total_revenue FROM sales WHERE sold_at >= CAST('2026-01-01' AS DATE) "
       "AND sold_at < CAST('2027-01-01' AS DATE)) AS t WHERE s.sold_at >= CAST('2026-01-01' AS DATE) "
       "AND s.sold_at < CAST('2027-01-01' AS DATE) GROUP BY b.name, t.total_revenue "
       "ORDER BY participacao_percentual DESC")
Q16 = ("WITH linhas AS (SELECT sl.sale_id, sl.quantity AS qtd FROM sale_lines AS sl JOIN products AS p "
       "ON p.id = sl.product_id WHERE p.name ILIKE '%pastel de nata%' UNION ALL SELECT sl.sale_id, "
       "sl.quantity * mi.quantity AS qtd FROM sale_lines AS sl JOIN menu_items AS mi ON mi.menu_id = sl.menu_id "
       "JOIN products AS p ON p.id = mi.product_id WHERE p.name ILIKE '%pastel de nata%') "
       "SELECT SUM(l.qtd) AS pasteis FROM linhas AS l JOIN sales AS s ON s.id = l.sale_id "
       "WHERE s.sold_at >= CAST('2026-10-01' AS DATE) AND s.sold_at < CAST('2026-11-01' AS DATE)")
MONTH = ("SELECT st.name, SUM(s.total) FROM sales AS s JOIN stores AS st ON st.id = s.store_id "
         "WHERE s.sold_at >= DATE_TRUNC('month', CURRENT_DATE) GROUP BY st.name")
QUERIES = {"q27_share_by_brand": Q27, "q16_pasteis_de_nata": Q16, "this_month_by_store": MONTH}


def test_timestamp_columns_match_the_database():
    """As colunas timestamp das tabelas com RLS que o assistente lê são TIMESTAMP_COLUMNS (só aí o
    problema existe: sem RLS o Postgres usa sempre as estatísticas)."""
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        rows = conn.execute("""
            SELECT DISTINCT c.column_name FROM information_schema.columns c
            JOIN pg_class t ON t.relname = c.table_name AND t.relnamespace = 'public'::regnamespace
            WHERE c.table_schema = 'public' AND c.data_type = 'timestamp without time zone'
              AND t.relrowsecurity
              AND has_column_privilege('assistente', format('%I.%I', c.table_schema, c.table_name),
                                       c.column_name, 'SELECT')""").fetchall()
    assert {r[0] for r in rows} == TIMESTAMP_COLUMNS


@pytest.mark.parametrize("username", ["pedro", "gestor.burgerlab", "gerente.maia"])
@pytest.mark.parametrize("name", QUERIES)
def test_eval_queries_are_fast_under_rls(users, username, name):
    sql = validate_sql(QUERIES[name])
    start = time.perf_counter()
    run_query(sql, users[username])
    assert time.perf_counter() - start < MAX_SECONDS


def _estimated_rows(sql: str) -> float:
    plan = run_query("EXPLAIN (FORMAT JSON) " + sql, IMPERADOR)[1][0][0]
    plan = plan if isinstance(plan, list) else json.loads(plan)
    return plan[0]["Plan"]["Plan Rows"]


def test_planner_estimates_rows_after_the_rewrite():
    """A causa: com DATE o planeador estima ~1 linha sob RLS; com TIMESTAMP estima o real."""
    raw = ("SELECT * FROM sales WHERE sold_at >= CAST('2026-01-01' AS DATE) "
           "AND sold_at < CAST('2027-01-01' AS DATE)")
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        real = conn.execute("SELECT count(*) FROM sales WHERE sold_at >= '2026-01-01' "
                            "AND sold_at < '2027-01-01'").fetchone()[0]
    assert _estimated_rows(raw) < real / 100                    # sem a correção: estimativa inútil
    assert _estimated_rows(validate_sql(raw)) > real / 3        # com a correção: ordem de grandeza certa


def test_rewrite_does_not_change_results(users):
    """A reescrita só muda o tipo do valor comparado: o resultado é o mesmo."""
    raw = ("SELECT count(*), sum(total) FROM sales WHERE sold_at >= CAST('2026-10-01' AS DATE) "
           "AND sold_at < CAST('2026-11-01' AS DATE)")
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:     # dono: sem RLS, plano normal
        expected = conn.execute(raw).fetchall()
    assert run_query(validate_sql(raw), IMPERADOR)[1] == expected
