"""O validador é a 1.ª barreira contra SQL perigoso escrito pelo LLM."""
import pytest

from multistore_ai_assistant.assistant.sql_validator import MAX_SQL_LENGTH, InvalidSQL, validate_sql, widen_ilike

ALLOWED = [
    "SELECT 1",
    "SELECT name FROM stores",
    "SELECT store_id, round(sum(total), 2) AS faturacao FROM sales GROUP BY store_id ORDER BY 2 DESC LIMIT 5",
    "WITH t AS (SELECT store_id, sum(total) AS v FROM sales GROUP BY 1) SELECT * FROM t",
    "SELECT * FROM price_recommendations WHERE classification = 'cão'",
    "SELECT date_trunc('month', sold_at) AS mes, count(*) FROM sales GROUP BY 1",
    "SELECT name FROM products WHERE name ILIKE '%burger%' UNION SELECT name FROM menus",
    "SELECT s.name, rank() OVER (ORDER BY sum(x.total) DESC) FROM stores s JOIN sales x ON x.store_id = s.id GROUP BY s.name",
    "SELECT current_date - INTERVAL '7 days'",
]


@pytest.mark.parametrize("sql", ALLOWED)
def test_accepts_read_only_queries(sql):
    assert validate_sql(sql)


def test_strips_trailing_semicolon_and_normalises():
    assert validate_sql("select 1;") == "SELECT 1"


BLOCKED = {
    # escrita / DDL
    "delete": "DELETE FROM sales",
    "update": "UPDATE products SET price = 0",
    "insert": "INSERT INTO brands (name) VALUES ('x')",
    "drop": "DROP TABLE sales",
    "truncate": "TRUNCATE sales",
    "alter": "ALTER TABLE sales ADD COLUMN x int",
    "create": "CREATE TABLE x (id int)",
    "select_into": "SELECT * INTO copia FROM sales",
    "for_update": "SELECT * FROM sales FOR UPDATE",
    "cte_delete": "WITH d AS (DELETE FROM sales RETURNING *) SELECT * FROM d",
    "copy": "COPY sales TO '/tmp/x.csv'",
    "set": "SET app.role = 'imperador'",
    # várias queries
    "multi": "SELECT 1; SELECT 2",
    "multi_write": "SELECT 1; DELETE FROM sales",
    # falsificar o perfil do RLS
    "set_config": "SELECT set_config('app.role', 'imperador', true)",
    "set_config_cte": "WITH x AS MATERIALIZED (SELECT set_config('app.role','imperador',true)) "
                      "SELECT count(*) FROM sales, x",
    "set_config_upper": "SELECT SET_CONFIG('app.store_id', '2', TRUE)",
    "current_setting": "SELECT current_setting('app.sig')",
    # executar SQL dentro de uma string
    "query_to_xml": "SELECT query_to_xml('select 1', true, true, '')",
    "table_to_xml": "SELECT table_to_xml('sales', true, true, '')",
    # ficheiros, rede, catálogo
    "pg_read_file": "SELECT pg_read_file('/etc/passwd')",
    "pg_sleep": "SELECT pg_sleep(100)",
    "lo_import": "SELECT lo_import('/etc/passwd')",
    "dblink": "SELECT * FROM dblink('host=evil', 'select 1') AS t(x int)",
    "pg_catalog": "SELECT * FROM pg_catalog.pg_roles",
    "pg_table": "SELECT * FROM pg_user",
    "information_schema": "SELECT * FROM information_schema.tables",
    # tabelas privadas
    "users": "SELECT password_hash FROM users",
    "app_secret": "SELECT key FROM app_secret",
    "role_features": "SELECT feature FROM role_features",
    "users_join": "SELECT s.name FROM stores s JOIN users u ON u.store_id = s.id",
    "hmac": "SELECT hmac('a', 'b', 'sha256')",
    # lixo
    "garbage": "isto não é SQL nenhum )))",
    "empty": "",
}


@pytest.mark.parametrize("sql", BLOCKED.values(), ids=BLOCKED.keys())
def test_blocks_dangerous_sql(sql):
    with pytest.raises(InvalidSQL):
        validate_sql(sql)


def test_rejects_very_long_sql():
    with pytest.raises(InvalidSQL, match="longo"):
        validate_sql("SELECT " + "1 + " * MAX_SQL_LENGTH + "1")


def test_error_message_names_the_function():
    with pytest.raises(InvalidSQL, match="set_config"):
        validate_sql("SELECT set_config('app.role', 'imperador', true)")


# ---------- colunas timestamp comparadas com timestamp (planos rápidos com RLS) ----------
# timestamp/date não é leakproof: com RLS o Postgres ignora as estatísticas e escolhe
# planos lentos. O validador troca o outro lado da comparação por timestamp (mesmo valor).

TIMESTAMP_REWRITES = {
    "cast_date": ("SELECT 1 FROM sales s WHERE s.sold_at >= CAST('2026-10-01' AS DATE)",
                  "SELECT 1 FROM sales AS s WHERE s.sold_at >= CAST('2026-10-01' AS TIMESTAMP)"),
    "date_literal": ("SELECT 1 FROM sales WHERE sold_at < DATE '2026-11-01'",
                     "SELECT 1 FROM sales WHERE sold_at < CAST('2026-11-01' AS TIMESTAMP)"),
    "string": ("SELECT 1 FROM sales WHERE sold_at >= '2026-01-01'",
               "SELECT 1 FROM sales WHERE sold_at >= CAST('2026-01-01' AS TIMESTAMP)"),
    "column_on_right": ("SELECT 1 FROM sales WHERE CAST('2026-01-01' AS DATE) <= sold_at",
                        "SELECT 1 FROM sales WHERE CAST('2026-01-01' AS TIMESTAMP) <= sold_at"),
    "current_date": ("SELECT 1 FROM sales WHERE sold_at >= CURRENT_DATE",
                     "SELECT 1 FROM sales WHERE sold_at >= CAST(CURRENT_DATE AS TIMESTAMP)"),
    "date_trunc": ("SELECT 1 FROM sales WHERE sold_at >= date_trunc('month', current_date)",
                   "SELECT 1 FROM sales WHERE sold_at >= CAST(DATE_TRUNC('MONTH', CURRENT_DATE) AS TIMESTAMP)"),
    "between": ("SELECT 1 FROM sales WHERE sold_at BETWEEN DATE '2026-01-01' AND '2026-01-31'",
                "SELECT 1 FROM sales WHERE sold_at BETWEEN CAST('2026-01-01' AS TIMESTAMP) "
                "AND CAST('2026-01-31' AS TIMESTAMP)"),
    "stock_updated_at": ("SELECT 1 FROM stock WHERE updated_at >= CAST('2026-11-01' AS DATE)",
                         "SELECT 1 FROM stock WHERE updated_at >= CAST('2026-11-01' AS TIMESTAMP)"),
    "inside_cte": ("WITH v AS (SELECT * FROM sales WHERE sold_at >= CAST('2026-01-01' AS DATE)) SELECT count(*) FROM v",
                   "WITH v AS (SELECT * FROM sales WHERE sold_at >= CAST('2026-01-01' AS TIMESTAMP)) "
                   "SELECT COUNT(*) FROM v"),
}


@pytest.mark.parametrize("sql,expected", TIMESTAMP_REWRITES.values(), ids=TIMESTAMP_REWRITES.keys())
def test_timestamp_columns_are_compared_with_timestamps(sql, expected):
    assert validate_sql(sql) == expected


UNCHANGED = {
    "date_column": "SELECT 1 FROM purchases WHERE ordered_at >= CAST('2026-01-01' AS DATE)",
    "column_vs_column": "SELECT 1 FROM sales AS s JOIN stock AS k ON k.updated_at > s.sold_at",
    "already_timestamp": "SELECT 1 FROM sales WHERE sold_at >= CAST('2026-01-01 10:00' AS TIMESTAMP)",
    "select_list": "SELECT DATE_TRUNC('MONTH', sold_at) AS mes FROM sales",
}


@pytest.mark.parametrize("sql", UNCHANGED.values(), ids=UNCHANGED.keys())
def test_other_comparisons_are_left_alone(sql):
    assert validate_sql(sql) == sql


# ---------- widen_ilike: 0 linhas com ILIKE sem % ----------

@pytest.mark.parametrize("sql,expected", [
    ("SELECT name FROM stores WHERE name ILIKE 'Maia'",
     "SELECT name FROM stores WHERE name ILIKE '%Maia%'"),
    ("SELECT 1 FROM stock AS s JOIN stores AS st ON st.id = s.store_id JOIN ingredients AS i ON i.id = s.ingredient_id "
     "WHERE st.name ILIKE 'coimbra' AND i.name ILIKE '%queijo%'",                         # só o que não tem %
     "SELECT 1 FROM stock AS s JOIN stores AS st ON st.id = s.store_id JOIN ingredients AS i ON i.id = s.ingredient_id "
     "WHERE st.name ILIKE '%coimbra%' AND i.name ILIKE '%queijo%'"),
    ("SELECT name FROM products WHERE name ILIKE 'Pastel d''Nata'",                         # aspas escapadas
     "SELECT name FROM products WHERE name ILIKE '%Pastel d''Nata%'"),
    ("SELECT name FROM stores WHERE id IN (SELECT store_id FROM sales) AND name ILIKE 'Porto'",
     "SELECT name FROM stores WHERE id IN (SELECT store_id FROM sales) AND name ILIKE '%Porto%'"),
])
def test_widen_ilike_adds_wildcards(sql, expected):
    assert widen_ilike(sql) == expected


@pytest.mark.parametrize("sql", [
    "SELECT name FROM stores WHERE name ILIKE '%Maia%'",                  # já alargado
    "SELECT name FROM stores WHERE name ILIKE 'Maia%'",                   # o LLM já escolheu o padrão
    "SELECT name FROM stores WHERE name ILIKE ''",                        # '%%' apanhava tudo
    "SELECT name FROM stores WHERE name NOT ILIKE 'Maia'",                # negado: daria menos linhas
    "SELECT name FROM stores WHERE NOT (name ILIKE 'Maia')",
    "SELECT name FROM stores AS st WHERE NOT EXISTS (SELECT 1 FROM brands AS b WHERE b.name ILIKE 'Gelato')",
    "SELECT name FROM stores WHERE name ILIKE ANY (ARRAY['Maia', 'Porto'])",
    "SELECT name FROM stores WHERE name LIKE 'Maia'",                     # LIKE: o LLM quis distinguir maiúsculas
    "SELECT name FROM stores WHERE name = 'Maia'",
    "isto não é SQL (",
])
def test_widen_ilike_leaves_everything_else_alone(sql):
    assert widen_ilike(sql) is None


def test_widened_sql_still_passes_the_validator():
    wider = widen_ilike("SELECT name FROM stores WHERE name ILIKE 'Maia' AND city ILIKE 'Maia'")
    assert validate_sql(wider) == wider

