"""Exemplos do RAG com a BD real: criar, editar (re-embedding), apagar e contar usos.

Os exemplos criados aqui começam por ``pytest`` e são apagados no fim.
"""
import os

import psycopg
import pytest

from multistore_ai_assistant.api import rag_examples
from multistore_ai_assistant.api.auth import load_user
from multistore_ai_assistant.api.errors import ApiError
from multistore_ai_assistant.assistant.examples import find_similar

pytestmark = pytest.mark.integration

try:
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=3) as _c:
        _ok = _c.execute("SELECT count(*) FROM information_schema.columns "
                         "WHERE table_name = 'sql_examples' AND column_name = 'uses'").fetchone()[0] == 1
except Exception:
    _ok = False
if not _ok:
    pytest.skip("Base de dados indisponível ou sem a migração V010__examples_admin.sql", allow_module_level=True)

SQL = "SELECT b.name AS marca, count(*) AS lojas FROM stores st JOIN brands b ON b.id = st.brand_id GROUP BY b.name"


@pytest.fixture
def admin():
    user = load_user("pedro")            # o perfil serve para o RLS do EXPLAIN; a permissão é testada nos unitários
    if user is None:
        pytest.skip("Conta de demo pedro não existe")
    return user


@pytest.fixture(autouse=True)
def cleanup():
    yield
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as c:
        c.execute("DELETE FROM sql_examples WHERE question ILIKE 'pytest%%'")


def get(example_id):
    return next(e for e in rag_examples.list_examples() if e["id"] == example_id)


def test_create_edit_and_delete(admin):
    eid = rag_examples.create("pytest quantas lojas tem cada marca", SQL, admin)
    created = get(eid)
    assert created["source"] == "manual" and created["created_by"] == "pedro" and created["uses"] == 0
    with pytest.raises(ApiError) as e:
        rag_examples.create("PYTEST quantas lojas tem cada marca", SQL, admin)
    assert e.value.code == "example_exists"

    rag_examples.update(eid, "pytest número de lojas por marca", SQL + " ORDER BY lojas DESC", admin)
    edited = get(eid)
    assert edited["question"] == "pytest número de lojas por marca" and edited["updated_by"] == "pedro"
    rag_examples.delete(eid)
    assert eid not in {e["id"] for e in rag_examples.list_examples()}


def test_editing_the_question_moves_the_embedding(admin):
    eid = rag_examples.create("pytest stock de pão em braga", "SELECT 1", admin)
    rag_examples.update(eid, "pytest quantas lojas tem cada marca do grupo", SQL, admin)
    assert any(q.startswith("pytest quantas lojas") for q, _ in find_similar("pytest quantas lojas tem cada marca"))


def test_broken_sql_is_not_saved(admin):
    with pytest.raises(ApiError) as e:
        rag_examples.create("pytest coluna inventada", "SELECT coluna_que_nao_existe FROM sales", admin)
    assert e.value.code == "sql_not_running"
    assert not any(x["question"] == "pytest coluna inventada" for x in rag_examples.list_examples())


def test_retrieval_counts_uses(admin):
    eid = rag_examples.create("pytest quantas lojas tem cada marca", SQL, admin)
    find_similar("pytest quantas lojas tem cada marca")
    find_similar("pytest quantas lojas tem cada marca")
    used = get(eid)
    assert used["uses"] == 2 and used["last_used_at"]


def test_unknown_example_is_404(admin):
    with pytest.raises(ApiError) as e:
        rag_examples.delete(-1)
    assert e.value.code == "example_not_found"


def test_source_must_be_known():
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as c, pytest.raises(psycopg.errors.CheckViolation):
        c.execute("INSERT INTO sql_examples (question, sql, embedding, source) "
                  "VALUES ('pytest x', 'SELECT 1', array_fill(0, ARRAY[384])::vector, 'outra')")
