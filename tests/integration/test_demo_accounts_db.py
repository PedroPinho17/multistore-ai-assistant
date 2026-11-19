"""Contas de demonstração com a BD real: a password é pública, por isso só leem nas contas."""
import os

import psycopg
import pytest

from multistore_ai_assistant.api import users
from multistore_ai_assistant.api.auth import load_user
from multistore_ai_assistant.api.permissions import AccessDenied, is_demo

pytestmark = pytest.mark.integration

try:
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=3) as _c:
        _ok = _c.execute("SELECT count(*) FROM users WHERE username = 'pedro' AND protected").fetchone()[0] == 1
except Exception:
    _ok = False
if not _ok:
    pytest.skip("Base de dados indisponível ou sem as contas de demonstração", allow_module_level=True)


@pytest.fixture
def real_account():
    """Uma conta 'real' de loja criada pelo admin (não é de demo)."""
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as c:
        admin = c.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1").fetchone()
        store = c.execute("SELECT id FROM stores ORDER BY id LIMIT 1").fetchone()[0]
        uid = c.execute("""INSERT INTO users (username, role, store_id, created_by, password_hash)
                           VALUES ('pytest.real', 'loja', %s, %s, 'x') RETURNING id""",
                        (store, admin[0] if admin else None)).fetchone()[0]
    yield uid
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as c:
        c.execute("DELETE FROM users WHERE username LIKE 'pytest.%%'")


@pytest.mark.parametrize("name", ["pedro", "gestor.burgerlab", "gerente.maia"])
def test_demo_accounts_are_flagged(name):
    assert is_demo(load_user(name))


def test_demo_imperador_cannot_take_over_a_real_account(real_account):
    pedro = load_user("pedro")
    for action in (lambda: users.update_user(pedro, real_account, password="Roubada-Pass-2026!"),
                   lambda: users.update_user(pedro, real_account, active=False),
                   lambda: users.delete_user(pedro, real_account),
                   lambda: users.create_user(pedro, "pytest.intruso", "Outra-Pass-2026!", "imperador", modules=["sql", "users"])):
        with pytest.raises(AccessDenied) as e:
            action()
        assert e.value.code == "demo_read_only"
    with psycopg.connect(os.environ["DATABASE_URL"]) as c:
        assert c.execute("SELECT active, password_hash FROM users WHERE id = %s", (real_account,)).fetchone() == (True, "x")
        assert c.execute("SELECT count(*) FROM users WHERE username = 'pytest.intruso'").fetchone()[0] == 0


def test_demo_imperador_still_sees_the_accounts(real_account):
    assert "pytest.real" in {u["username"] for u in users.list_users(load_user("pedro"))}
    assert users.options(load_user("pedro"))["read_only"] is True
