"""Perfil na BD real, com um utilizador temporário (as contas demo não são tocadas)."""
import os

import bcrypt
import psycopg
import pytest

from multistore_ai_assistant.api import conversations as conv
from multistore_ai_assistant.api.auth import authenticate
from multistore_ai_assistant.api.profile import PasswordError, change_password, delete_all_conversations, get_profile

pytestmark = pytest.mark.integration
TMP = "pytest.temporario"

try:
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=3) as _c:
        _ok = _c.execute("SELECT to_regclass('public.conversations') IS NOT NULL").fetchone()[0]
except Exception:
    _ok = False
if not _ok:
    pytest.skip("Base de dados indisponível", allow_module_level=True)


@pytest.fixture
def tmp_user():
    """Gerente de loja temporário, criado e apagado pelo teste."""
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as c:
        store_id, brand = c.execute(
            "SELECT s.id, b.name FROM stores s JOIN brands b ON b.id = s.brand_id ORDER BY s.id LIMIT 1").fetchone()
        c.execute("DELETE FROM users WHERE username = %s", (TMP,))
        c.execute("INSERT INTO users (username, password_hash, role, store_id) VALUES (%s, %s, 'loja', %s)",
                  (TMP, bcrypt.hashpw(b"Inicial2026", bcrypt.gensalt(rounds=4)).decode(), store_id))
        yield {"username": TMP, "role": "loja", "brand_id": None, "store_id": store_id, "brand": brand}
        c.execute("DELETE FROM users WHERE username = %s", (TMP,))


def test_profile_of_a_new_user(tmp_user):
    p = get_profile({k: tmp_user[k] for k in ("username", "role", "brand_id", "store_id")})
    assert p["store_name"] and p["brand_name"] == tmp_user["brand"]
    assert p["visible_stores"] == 1
    assert p["stats"] == {"conversations": 0, "questions": 0, "last_activity": None,
                          "first_activity": None, "by_kind": {}}


def test_profile_stats_count_my_activity(tmp_user):
    cid = conv.create_conversation(TMP, "Vendas?")
    conv.add_message(cid, "user", "Vendas?")
    conv.add_message(cid, "assistant", "10 €", "SELECT 1", "sql")
    conv.add_message(cid, "user", "E amanhã?")
    conv.add_message(cid, "assistant", "5 €", None, "forecast")
    stats = get_profile({k: tmp_user[k] for k in ("username", "role", "brand_id", "store_id")})["stats"]
    assert (stats["conversations"], stats["questions"]) == (1, 2)
    assert stats["by_kind"] == {"sql": 1, "forecast": 1}
    assert stats["last_activity"] is not None


def test_imperador_and_brand_scope():
    p = get_profile({"username": "pedro", "role": "imperador", "brand_id": None, "store_id": None})
    assert p["visible_stores"] >= 1 and p["brand_name"] is None
    with psycopg.connect(os.environ["DATABASE_URL"]) as c:
        brand_id, name, n = c.execute("""SELECT b.id, b.name, count(s.id) FROM brands b
                                         JOIN stores s ON s.brand_id = b.id GROUP BY b.id ORDER BY b.id LIMIT 1""").fetchone()
    p = get_profile({"username": "x", "role": "marca", "brand_id": brand_id, "store_id": None})
    assert (p["brand_name"], p["visible_stores"]) == (name, n)


def test_change_password_roundtrip(tmp_user):
    with pytest.raises(PasswordError):
        change_password(TMP, "errada", "Nova2026pass")
    change_password(TMP, "Inicial2026", "Nova2026pass")
    assert authenticate(TMP, "Nova2026pass")
    assert authenticate(TMP, "Inicial2026") is None


def test_delete_all_only_touches_my_conversations(tmp_user):
    mine = [conv.create_conversation(TMP, f"q{i}") for i in range(3)]
    other = conv.create_conversation("gerente.maia", "não apagar")
    try:
        assert delete_all_conversations(TMP) == 3
        assert all(not conv.owns(TMP, c) for c in mine)
        assert conv.owns("gerente.maia", other)
    finally:
        conv.delete_conversation("gerente.maia", other)
