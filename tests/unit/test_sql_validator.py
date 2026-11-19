"""O validador é a 1.ª barreira contra SQL perigoso escrito pelo LLM."""
import pytest

from multistore_ai_assistant.assistant.sql_validator import MAX_SQL_LENGTH, InvalidSQL, validate_sql

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
