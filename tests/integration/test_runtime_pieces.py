"""Peças que correm em cada pergunta: schema para o prompt, RAG e previsão (BD real)."""
import os

import psycopg
import pytest

from multistore_ai_assistant.db.schema import get_schema_text
from multistore_ai_assistant.forecast.train import MODEL_PATH as FORECAST_MODEL
from tests.conftest import IMPERADOR, LOJA

pytestmark = pytest.mark.integration

try:
    with psycopg.connect(os.environ["READONLY_DATABASE_URL"], connect_timeout=3):
        pass
except Exception:
    pytest.skip("Base de dados indisponível", allow_module_level=True)


@pytest.fixture(scope="module")
def schema() -> str:
    return get_schema_text()


def test_schema_lists_tables_views_and_foreign_keys(schema):
    assert "sales(" in schema and "price_recommendations(" in schema
    assert "store_id integer -> stores.id" in schema


@pytest.mark.parametrize("column,value", [
    ("sales.payment_method", "'mbway'"), ("purchases.status", "'recebida'"),
    ("products.category", "'bebida'"), ("employees.contract_type", "'part-time'"),
])
def test_schema_includes_category_values(schema, column, value):
    """Regressão: com o RLS, estas listas vinham vazias e o LLM tinha de adivinhar os valores."""
    line = next(line for line in schema.splitlines() if line.startswith(f"- {column}:"))
    assert value in line


@pytest.mark.parametrize("table", ["users(", "app_secret(", "conversations(", "messages("])
def test_schema_sent_to_the_llm_hides_private_tables(schema, table):
    """O LLM só vê o que o role 'assistente' pode ler."""
    assert table not in schema


@pytest.mark.parametrize("column", ["nif", "niss", "birth_date", "address"])
def test_schema_hides_personal_employee_columns(schema, column):
    employees = next(line for line in schema.splitlines() if line.startswith("employees("))
    assert column not in employees


def test_schema_is_cached(monkeypatch):
    from multistore_ai_assistant.db import schema as schema_mod
    schema_mod.get_schema_text()
    monkeypatch.setattr(schema_mod, "_build_schema_text", lambda: pytest.fail("devia vir da cache"))
    assert "sales(" in schema_mod.get_schema_text()


@pytest.mark.model
def test_rag_finds_a_similar_example():
    from multistore_ai_assistant.assistant.examples import find_similar
    results = find_similar("Qual foi a faturação de cada marca no mês passado?")
    assert results and all(sql.upper().startswith(("SELECT", "WITH")) for _, sql in results)


@pytest.mark.model
def test_rag_ignores_unrelated_text():
    from multistore_ai_assistant.assistant.examples import find_similar
    assert find_similar("receita de bolo de chocolate com morangos") == []


@pytest.mark.model
@pytest.mark.skipif(not FORECAST_MODEL.exists(), reason="Modelo de previsão não treinado")
def test_forecast_next_7_days_per_store():
    from multistore_ai_assistant.forecast.predict import forecast
    df = forecast(7)
    assert df["day"].nunique() == 7
    assert df.groupby("day")["store_id"].nunique().min() >= 1
    assert (df["revenue"] >= 0).all()


@pytest.mark.model
@pytest.mark.skipif(not FORECAST_MODEL.exists(), reason="Modelo de previsão não treinado")
def test_forecast_and_orders_respect_the_profile():
    from multistore_ai_assistant.forecast.service import forecast_answer, orders_answer
    group = sum(v for _, v in forecast_answer(IMPERADOR)[1])
    store = sum(v for _, v in forecast_answer(LOJA)[1])
    assert 0 < store < group
    columns, rows = orders_answer(LOJA)
    assert columns[0] == "ingredient" and all(r[-1] >= 0 for r in rows)
