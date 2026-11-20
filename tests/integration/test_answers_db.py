"""Gravação das respostas na BD real: NaN/Infinity nas linhas e pergunta + resposta numa transação.

Antes: uma resposta com NaN nas linhas (p.ex. uma previsão sem histórico) fazia o ``jsonb``
recusar a mensagem; o /ask dava 500, o /ask/stream acabava em erro e a pergunta ficava
gravada sem resposta. O LLM é simulado (devolve as linhas com NaN); a BD é a real.
"""
import json
import os
from decimal import Decimal

import bcrypt
import psycopg
import pytest
from fastapi.testclient import TestClient

from multistore_ai_assistant.api import auth
from multistore_ai_assistant.api import conversations as conv
from multistore_ai_assistant.api import main as api
from multistore_ai_assistant.api.routes import ask as ask_route

pytestmark = pytest.mark.integration
TMP = "pytest.respostas"

try:
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=3) as _c:
        _ok = _c.execute("""SELECT EXISTS (SELECT FROM information_schema.columns
                            WHERE table_name = 'messages' AND column_name = 'result')""").fetchone()[0]
except Exception:
    _ok = False
if not _ok:
    pytest.skip("Base de dados indisponível ou sem a migração V014__message_results.sql", allow_module_level=True)

client = TestClient(api.app)
ROWS = [["Pão", float("nan")], ["Carne", float("inf")], ["Leite", Decimal("NaN")], ["Ovos", 12.5]]
CLEAN = [["Pão", None], ["Carne", None], ["Leite", None], ["Ovos", 12.5]]


def owner():
    return psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)


@pytest.fixture
def user(monkeypatch):
    with owner() as c:
        c.execute("DELETE FROM users WHERE username = %s", (TMP,))
        c.execute("INSERT INTO users (username, password_hash, role, store_id) VALUES (%s, %s, 'loja', 1)",
                  (TMP, bcrypt.hashpw(b"x", bcrypt.gensalt(rounds=4)).decode()))
    monkeypatch.setattr(ask_route, "ask", lambda q, u, lang, h, on_event=None: {
        "sql": None, "kind": "orders", "columns": ["ingredient", "to_order"], "rows": ROWS,
        "answer": "Encomenda ovos."})
    yield auth.load_user(TMP)
    with owner() as c:
        c.execute("DELETE FROM users WHERE username = %s", (TMP,))   # conversas e mensagens vão em cascata


def headers(user) -> dict:
    return {"Authorization": "Bearer " + auth.create_token(user)}


def saved(conversation_id: int) -> list[tuple]:
    with owner() as c:
        return c.execute("SELECT role, content, result FROM messages WHERE conversation_id = %s ORDER BY id",
                         (conversation_id,)).fetchall()


def test_nan_rows_through_ask_are_saved_with_both_messages(user):
    r = client.post("/ask", json={"question": "O que encomendar?", "lang": "pt"}, headers=headers(user))
    assert r.status_code == 200 and r.json()["rows"] == CLEAN
    messages = saved(r.json()["conversation_id"])
    assert [(m[0], m[1]) for m in messages] == [("user", "O que encomendar?"), ("assistant", "Encomenda ovos.")]
    assert messages[1][2] == {"columns": ["ingredient", "to_order"], "rows": CLEAN, "truncated": False}


def test_nan_rows_through_the_stream_are_saved_with_both_messages(user):
    r = client.post("/ask/stream", json={"question": "O que encomendar?", "lang": "pt"}, headers=headers(user))
    assert "NaN" not in r.text and "Infinity" not in r.text
    events = [json.loads(x[len("data: "):]) for x in r.text.split("\n\n") if x.startswith("data: ")]
    done = events[-1]
    assert done["type"] == "done" and done["rows"] == CLEAN
    messages = saved(done["conversation_id"])
    assert [m[0] for m in messages] == ["user", "assistant"] and messages[1][2]["rows"] == CLEAN


def test_the_question_and_the_answer_are_one_transaction(user):
    """Se a resposta for recusada pela BD, a pergunta também não fica (nada de perguntas órfãs)."""
    cid = conv.create_conversation(TMP, "Transação")
    too_big = json.dumps({"columns": ["n"], "rows": [[i] for i in range(201)], "truncated": False})
    with pytest.raises(psycopg.errors.CheckViolation):
        conv.add_exchange(cid, "Pergunta?", "Resposta.", None, "sql", None, too_big)
    assert saved(cid) == []
    conv.add_exchange(cid, "Pergunta?", "Resposta.", None, "sql", None, conv.result_payload(["n"], [(1,)]))
    assert [m[0] for m in saved(cid)] == ["user", "assistant"]
