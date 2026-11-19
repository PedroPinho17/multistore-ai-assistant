"""Cache de SQL, SQL de uma resposta (/explain) e alertas com a BD real.

As entradas da cache criadas aqui têm perguntas começadas por ``pytest`` e são
apagadas no fim.
"""
import os

import psycopg
import pytest

from multistore_ai_assistant.api import alerts, conversations
from multistore_ai_assistant.api.auth import load_user
from multistore_ai_assistant.assistant import cache

pytestmark = pytest.mark.integration

try:
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=3) as _c:
        _ok = _c.execute("SELECT to_regclass('public.query_cache') IS NOT NULL").fetchone()[0]
except Exception:
    _ok = False
if not _ok:
    pytest.skip("Base de dados indisponível ou sem a migração V007__semantic_cache.sql", allow_module_level=True)

LOJA = {"username": "pytest.loja", "role": "loja", "brand_id": 1, "store_id": 1}
MARCA = {"username": "pytest.marca", "role": "marca", "brand_id": 1, "store_id": None}
Q = "pytest faturação total de cada marca em outubro de 2026"


def owner():
    return psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)


@pytest.fixture(autouse=True)
def cleanup():
    yield
    with owner() as c:
        c.execute("DELETE FROM query_cache WHERE question LIKE 'pytest%'")


def test_similar_question_same_scope_hits():
    cache.store(Q, "SELECT 42", LOJA)
    hit = cache.lookup("pytest faturação total de cada marca em outubro 2026", LOJA)
    assert hit and hit["sql"] == "SELECT 42" and hit["distance"] <= cache.MAX_DISTANCE
    with owner() as c:
        assert c.execute("SELECT hits FROM query_cache WHERE question = %s", (Q,)).fetchone()[0] == 1


def test_other_scope_or_different_question_misses():
    cache.store(Q, "SELECT 42", LOJA)
    assert cache.lookup(Q, MARCA) is None                                         # outro perfil
    assert cache.lookup("pytest quantos funcionários tem cada loja?", LOJA) is None


def test_entries_from_yesterday_are_ignored():
    cache.store(Q, "SELECT 42", LOJA)
    with owner() as c:
        c.execute("UPDATE query_cache SET created_at = now() - interval '1 day' WHERE question = %s", (Q,))
    assert cache.lookup(Q, LOJA) is None


def test_the_readonly_role_cannot_read_the_cache():
    from multistore_ai_assistant.db.query import run_query
    with pytest.raises(psycopg.Error):
        run_query("SELECT sql FROM query_cache", {**LOJA})


def test_sql_of_request_only_for_the_owner():
    with owner() as c:
        rid = c.execute("SELECT m.request_id, u.username FROM messages m JOIN conversations cv ON cv.id = m.conversation_id "
                        "JOIN users u ON u.id = cv.user_id WHERE m.request_id IS NOT NULL AND m.sql IS NOT NULL "
                        "LIMIT 1").fetchone()
    if not rid:
        pytest.skip("Sem respostas com SQL gravadas")
    request_id, username = rid
    assert conversations.sql_of_request(username, request_id)
    assert conversations.sql_of_request("ninguem.pytest", request_id) is None


def test_alerts_respect_the_store_scope():
    user = load_user("gerente.maia")
    if user is None:
        pytest.skip("Conta de demo gerente.maia não existe")
    alerts.clear_cache()
    items = alerts.alerts_for(user, "pt")
    assert all("Maia" in a["store"] for a in items)
    alerts.clear_cache()


def test_other_month_or_year_misses_even_when_embeddings_are_close():
    cache.store(Q, "SELECT 42", LOJA)
    assert cache.lookup("pytest faturação total de cada marca em novembro de 2026", LOJA) is None
    assert cache.lookup("pytest faturação total de cada marca em outubro de 2025", LOJA) is None


def test_rewording_in_another_language_hits():
    cache.store(Q, "SELECT 42", LOJA)
    hit = cache.lookup("pytest revenue of each brand in October 2026", LOJA)
    assert hit and hit["sql"] == "SELECT 42"


def test_more_vs_less_misses_although_the_embedding_is_close():
    question = "pytest quais as 5 lojas com mais faturação em 2026"
    cache.store(question, "SELECT 1", LOJA)
    assert cache.lookup("pytest quais as 5 lojas com menos faturação em 2026", LOJA) is None
    assert cache.lookup(question, LOJA)["sql"] == "SELECT 1"
