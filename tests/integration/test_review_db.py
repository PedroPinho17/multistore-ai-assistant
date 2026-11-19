"""Revisão dos 👎 com a BD real: lista, ensinar (entra no RAG) e ignorar; ambos tiram da lista.

Tudo o que é criado aqui tem ``pytest`` no nome/pergunta e é apagado no fim.
"""
import os

import psycopg
import pytest

from multistore_ai_assistant.api import review
from multistore_ai_assistant.api.auth import load_user
from multistore_ai_assistant.api.errors import ApiError

pytestmark = pytest.mark.integration

try:
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=3) as _c:
        _ok = _c.execute("SELECT count(*) FROM information_schema.columns "
                         "WHERE table_name = 'request_log' AND column_name = 'reviewed_at'").fetchone()[0] == 1
except Exception:
    _ok = False
if not _ok:
    pytest.skip("Base de dados indisponível ou sem a migração V008__review.sql", allow_module_level=True)

SQL = "SELECT b.name AS marca, count(*) AS lojas FROM stores st JOIN brands b ON b.id = st.brand_id GROUP BY b.name"


def owner():
    return psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)


@pytest.fixture
def imperador():
    user = load_user("pedro")
    if user is None:
        pytest.skip("Conta de demo pedro não existe")
    return user


@pytest.fixture
def thumbs_down(imperador):
    """Duas trocas numa conversa: a 2.ª é um seguimento. Ambas com 👎."""
    with owner() as c:
        conv = c.execute("INSERT INTO conversations (user_id, title) VALUES (%s, 'pytest review') RETURNING id",
                         (imperador["id"],)).fetchone()[0]
        ids = []
        for question, kind in (("pytest quantas lojas tem cada marca", "sql"), ("pytest e só da BurgerLab?", "sql"),
                               ("pytest quanto vou vender", "forecast")):
            rid = c.execute(
                """INSERT INTO request_log (username, role, conversation_id, question, lang, kind, duration_ms, rating)
                   VALUES ('pytest.review', 'loja', %s, %s, 'pt', %s, 100, -1) RETURNING id""",
                (conv, question, kind)).fetchone()[0]
            c.execute("INSERT INTO messages (conversation_id, role, content, sql, kind, request_id) "
                      "VALUES (%s, 'assistant', 'resposta errada', %s, %s, %s)",
                      (conv, "SELECT 1" if kind == "sql" else None, kind, rid))
            ids.append(rid)
    yield ids
    with owner() as c:
        c.execute("DELETE FROM request_log WHERE username = 'pytest.review'")
        c.execute("DELETE FROM conversations WHERE id = %s", (conv,))
        c.execute("DELETE FROM sql_examples WHERE question LIKE 'pytest%%'")


def listed(ids):
    return {i["id"]: i for i in review.pending()["items"] if i["id"] in ids}


def test_list_has_question_sql_and_follow_up_flag(thumbs_down):
    items = listed(thumbs_down)
    first, follow, forecast = (items[i] for i in thumbs_down)
    assert first["sql"] == "SELECT 1" and first["answer"] == "resposta errada" and not first["follow_up"]
    assert follow["follow_up"] and first["can_teach"] and not forecast["can_teach"]


def test_teaching_adds_the_example_and_leaves_the_list(thumbs_down, imperador):
    review.teach(thumbs_down[0], "pytest quantas lojas tem cada marca", SQL, imperador)
    assert thumbs_down[0] not in listed(thumbs_down)
    with owner() as c:
        example = c.execute("SELECT sql, source FROM sql_examples WHERE question = 'pytest quantas lojas tem cada marca'").fetchone()
        log = c.execute("SELECT review_action, reviewed_by FROM request_log WHERE id = %s", (thumbs_down[0],)).fetchone()
    assert example[1] == "review" and "GROUP BY" in example[0]
    assert log == ("taught", "pedro")


def test_dismissing_leaves_the_list_without_an_example(thumbs_down, imperador):
    review.dismiss(thumbs_down[2], imperador)
    assert thumbs_down[2] not in listed(thumbs_down)
    with owner() as c:
        assert c.execute("SELECT count(*) FROM sql_examples WHERE question LIKE 'pytest%%'").fetchone()[0] == 0


def test_invalid_or_broken_sql_keeps_it_in_the_list(thumbs_down, imperador):
    for sql, code in (("DELETE FROM sales", "invalid_sql"), ("SELECT coluna_que_nao_existe FROM sales", "sql_not_running")):
        with pytest.raises(ApiError) as e:
            review.teach(thumbs_down[0], "pytest x", sql, imperador)
        assert e.value.code == code
    assert thumbs_down[0] in listed(thumbs_down)


def test_preview_returns_rows_under_the_reviewer_rls(thumbs_down, imperador):
    out = review.preview(thumbs_down[0], SQL, imperador)
    assert out["columns"] == ["marca", "lojas"] and out["row_count"] == 3


def test_reviewing_twice_is_refused(thumbs_down, imperador):
    review.dismiss(thumbs_down[1], imperador)
    with pytest.raises(ApiError) as e:
        review.dismiss(thumbs_down[1], imperador)
    assert e.value.code == "review_not_found"


def test_review_columns_must_be_consistent():
    with owner() as c, pytest.raises(psycopg.errors.CheckViolation):
        c.execute("""INSERT INTO request_log (username, role, question, lang, kind, duration_ms, review_action)
                     VALUES ('pytest.review', 'loja', 'q', 'pt', 'sql', 1, 'taught')""")


def test_the_public_imperador_demo_account_cannot_teach():
    """A password do 'pedro' está no README: ensinar (RAG e /review) fica só para a conta admin privada."""
    from multistore_ai_assistant.api.permissions import has_module
    user = load_user("pedro")
    if user is None:
        pytest.skip("Conta de demo pedro não existe")
    assert not has_module(user, "teach") and has_module(user, "sql") and has_module(user, "users")


def test_teach_is_atomic_when_marking_fails(thumbs_down, imperador, monkeypatch):
    """Se tirar o 👎 da lista falhar, o exemplo também não fica (mesma transação)."""
    def boom(*a, **k):
        raise RuntimeError("falha a meio")
    monkeypatch.setattr(review, "_mark", boom)
    with pytest.raises(RuntimeError):
        review.teach(thumbs_down[0], "pytest exemplo que não pode ficar", SQL, imperador)
    with owner() as c:
        assert c.execute("SELECT count(*) FROM sql_examples WHERE question = 'pytest exemplo que não pode ficar'").fetchone()[0] == 0
    assert thumbs_down[0] in listed(thumbs_down)


def test_teach_rolls_back_if_someone_reviewed_it_meanwhile(thumbs_down, imperador, monkeypatch):
    """Outra pessoa ignorou o 👎 entre a leitura e a gravação: nada fica gravado."""
    review.dismiss(thumbs_down[0], imperador)
    monkeypatch.setattr(review, "_get_pending", lambda rid: {"id": rid, "kind": "sql"})   # leu antes do outro
    with pytest.raises(ApiError) as e:
        review.teach(thumbs_down[0], "pytest exemplo atrasado", SQL, imperador)
    assert e.value.code == "review_not_found"
    with owner() as c:
        assert c.execute("SELECT count(*) FROM sql_examples WHERE question = 'pytest exemplo atrasado'").fetchone()[0] == 0
