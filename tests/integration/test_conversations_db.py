"""Conversas guardadas na BD real: cada utilizador só vê e mexe nas suas."""
import os

import psycopg
import pytest

from multistore_ai_assistant.api import conversations as conv

pytestmark = pytest.mark.integration


def _ready() -> bool:
    try:
        with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=3) as c:
            return c.execute("SELECT to_regclass('public.conversations') IS NOT NULL").fetchone()[0]
    except Exception:
        return False


if not _ready():
    pytest.skip("Base de dados indisponível ou sem a migração V004__conversations.sql", allow_module_level=True)


@pytest.fixture
def conversation():
    cid = conv.create_conversation("gerente.maia", "Teste automático " + "x" * 80)
    yield cid
    conv.delete_conversation("gerente.maia", cid)


def test_title_is_truncated(conversation):
    title = next(c["title"] for c in conv.list_conversations("gerente.maia") if c["id"] == conversation)
    assert len(title) == 61 and title.endswith("…")


def test_owner_checks(conversation):
    assert conv.owns("gerente.maia", conversation)
    assert not conv.owns("pedro", conversation)
    assert not conv.owns("nao.existe", conversation)


def test_other_users_cannot_read_rename_or_delete(conversation):
    assert conv.get_messages("pedro", conversation) is None
    assert conv.rename_conversation("pedro", conversation, "roubada") is False
    assert conv.delete_conversation("pedro", conversation) is False
    assert conversation not in [c["id"] for c in conv.list_conversations("pedro")]
    assert conv.owns("gerente.maia", conversation)


def test_messages_and_history_roundtrip(conversation):
    conv.add_message(conversation, "user", "Vendas em outubro?")
    conv.add_message(conversation, "assistant", "10 €", "SELECT 1", "sql")
    conv.add_message(conversation, "user", "E para a semana?")
    conv.add_message(conversation, "assistant", "5 €", None, "forecast")
    msgs = conv.get_messages("gerente.maia", conversation)
    assert [(m["role"], m["content"]) for m in msgs] == [
        ("user", "Vendas em outubro?"), ("assistant", "10 €"), ("user", "E para a semana?"), ("assistant", "5 €")]
    assert conv.get_history(conversation) == [("Vendas em outubro?", "SELECT 1"), ("E para a semana?", "FORECAST")]


def test_history_keeps_only_the_last_turns(conversation):
    for i in range(5):
        conv.add_message(conversation, "user", f"q{i}")
        conv.add_message(conversation, "assistant", f"a{i}", f"SELECT {i}", "sql")
    assert [q for q, _ in conv.get_history(conversation, turns=3)] == ["q2", "q3", "q4"]


def test_rename_and_delete_cascade(conversation):
    conv.add_message(conversation, "user", "olá")
    assert conv.rename_conversation("gerente.maia", conversation, "  Novo nome  ")
    assert next(c["title"] for c in conv.list_conversations("gerente.maia") if c["id"] == conversation) == "Novo nome"
    assert conv.delete_conversation("gerente.maia", conversation)
    with psycopg.connect(os.environ["DATABASE_URL"]) as c:
        assert c.execute("SELECT count(*) FROM messages WHERE conversation_id = %s",
                         (conversation,)).fetchone()[0] == 0
