"""Recuperação de password na BD real, com uma conta temporária (as contas demo não mudam)."""
import os

import bcrypt
import psycopg
import pytest
from fastapi.testclient import TestClient

from multistore_ai_assistant.api import mailer
from multistore_ai_assistant.api import main as api
from multistore_ai_assistant.api.auth import authenticate
from multistore_ai_assistant.api.errors import ApiError
from multistore_ai_assistant.api.password_reset import request_reset, reset_password, token_hash
from multistore_ai_assistant.api.permissions import AccessDenied
from multistore_ai_assistant.api.users import set_email
from multistore_ai_assistant.db.query import run_query
from tests.conftest import IMPERADOR

pytestmark = pytest.mark.integration
TMP, EMAIL = "pytest.recupera", "pytest.recupera@exemplo.pt"

try:
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=3) as _c:
        _ok = _c.execute("SELECT to_regclass('public.password_resets') IS NOT NULL").fetchone()[0]
except Exception:
    _ok = False
if not _ok:
    pytest.skip("Base de dados indisponível ou sem a migração V011", allow_module_level=True)


def db():
    return psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)


@pytest.fixture
def user():
    with db() as c:
        store_id = c.execute("SELECT id FROM stores ORDER BY id LIMIT 1").fetchone()[0]
        c.execute("DELETE FROM users WHERE username = %s", (TMP,))
        uid = c.execute(
            "INSERT INTO users (username, password_hash, role, store_id, email) VALUES (%s, %s, 'loja', %s, %s) "
            "RETURNING id", (TMP, bcrypt.hashpw(b"Antiga2026", bcrypt.gensalt(rounds=4)).decode(), store_id, EMAIL),
        ).fetchone()[0]
        yield uid
        c.execute("DELETE FROM users WHERE username = %s", (TMP,))     # os tokens vão em cascata


def resets(uid):
    with db() as c:
        return c.execute("SELECT token_hash, expires_at - created_at, used_at FROM password_resets "
                         "WHERE user_id = %s ORDER BY id", (uid,)).fetchall()


def test_full_flow_by_email(user):
    found = request_reset(EMAIL.upper())                       # o email não distingue maiúsculas
    assert found["username"] == TMP and found["email"] == EMAIL
    assert reset_password(found["token"], "NovaPass2026") == TMP
    assert authenticate(TMP, "NovaPass2026") and not authenticate(TMP, "Antiga2026")


def test_request_by_username_also_works(user):
    assert request_reset(TMP)["email"] == EMAIL


def test_only_the_hash_is_stored_and_it_expires_in_30_minutes(user):
    token = request_reset(EMAIL)["token"]
    [(stored, validity, used)] = resets(user)
    assert stored == token_hash(token) and token not in stored
    assert validity.total_seconds() == 30 * 60 and used is None


def test_token_is_single_use(user):
    token = request_reset(EMAIL)["token"]
    reset_password(token, "NovaPass2026")
    with pytest.raises(ApiError) as e:
        reset_password(token, "OutraPass2026")
    assert e.value.code == "reset_invalid"


def test_a_new_request_cancels_the_previous_link(user):
    old = request_reset(EMAIL)["token"]
    new = request_reset(EMAIL)["token"]
    with pytest.raises(ApiError, match="reset_invalid"):
        reset_password(old, "NovaPass2026")
    assert reset_password(new, "NovaPass2026") == TMP


def test_expired_token_is_refused(user):
    token = request_reset(EMAIL)["token"]
    with db() as c:
        c.execute("UPDATE password_resets SET expires_at = now() - interval '1 second' WHERE user_id = %s", (user,))
    with pytest.raises(ApiError, match="reset_invalid"):
        reset_password(token, "NovaPass2026")


def test_unknown_token_is_refused():
    with pytest.raises(ApiError, match="reset_invalid"):
        reset_password("nao-existe-" + "x" * 32, "NovaPass2026")


def test_weak_password_keeps_the_token(user):
    token = request_reset(EMAIL)["token"]
    with pytest.raises(ApiError) as e:
        reset_password(token, "curta")
    assert e.value.code == "pw_too_short"
    assert reset_password(token, "NovaPass2026") == TMP          # o link continua válido


def test_disabled_account_gets_no_link(user):
    with db() as c:
        c.execute("UPDATE users SET active = false WHERE id = %s", (user,))
    assert request_reset(EMAIL) is None


def test_unknown_email_gets_no_link():
    assert request_reset("ninguem@exemplo.pt") is None


@pytest.mark.parametrize("demo", ["pedro", "gestor.burgerlab", "gerente.maia"])
def test_demo_accounts_cannot_reset(demo):
    with pytest.raises(ApiError) as e:
        request_reset(demo)
    assert (e.value.code, e.value.status) == ("reset_demo", 403)


def test_demo_accounts_cannot_have_an_email():
    with db() as c:
        uid = c.execute("SELECT id FROM users WHERE username = 'pedro'").fetchone()[0]
        with pytest.raises(AccessDenied) as e:
            set_email(c, uid, "pedro@exemplo.pt")
    assert e.value.code == "demo_no_email"


def test_email_is_unique_ignoring_case(user):
    with db() as c:
        other = c.execute("SELECT id FROM users WHERE username = 'pedro'").fetchone()[0]
        c.execute("UPDATE users SET protected = false WHERE id = %s", (other,))
        try:
            with pytest.raises(AccessDenied) as e:
                set_email(c, other, EMAIL.upper())
            assert e.value.code == "email_taken"
        finally:
            c.execute("UPDATE users SET protected = true, email = NULL WHERE id = %s", (other,))


def test_the_assistant_role_cannot_read_reset_tokens(user):
    request_reset(EMAIL)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        run_query("SELECT token_hash FROM password_resets", IMPERADOR)


def test_end_to_end_through_the_api(user, monkeypatch):
    """/password/forgot → email com o link → /password/reset com o token do link."""
    sent = []
    monkeypatch.setattr(mailer, "send", lambda msg: sent.append(msg) or True)
    client = TestClient(api.app)
    assert client.post("/password/forgot", json={"login": EMAIL, "lang": "pt"}).json() == {"ok": True}
    assert len(sent) == 1 and sent[0]["To"] == EMAIL
    token = sent[0].get_content().split("reset-password#token=")[1].split()[0]
    r = client.post("/password/reset", json={"token": token, "new_password": "NovaPass2026"})
    assert r.status_code == 200
    assert client.post("/login", json={"username": TMP, "password": "NovaPass2026"}).status_code == 200
