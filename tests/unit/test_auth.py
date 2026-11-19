import base64
import json
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
import pytest
from fastapi.security import HTTPAuthorizationCredentials

from multistore_ai_assistant.api import auth
from multistore_ai_assistant.api.errors import ApiError
from tests.conftest import LOJA
from tests.unit.conftest import REAL_LOAD_USER


def creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


# ---------- JWT ----------

def test_token_roundtrip():
    token = auth.create_token(LOJA)
    assert auth.current_user(creds(token)) == LOJA


def test_token_only_carries_identity():
    """Âmbito e módulos não vão no token: vêm da BD em cada pedido."""
    payload = jwt.decode(auth.create_token(LOJA), auth.SECRET, algorithms=["HS256"])
    assert set(payload) == {"sub", "role", "iat", "exp"}


def test_profile_comes_from_the_database_not_the_token(fake_users):
    """Mudar o perfil na BD tem efeito logo, mesmo com um token antigo."""
    token = auth.create_token(LOJA)
    fake_users["gerente.maia"]["modules"] = ["sql"]
    assert auth.current_user(creds(token))["modules"] == ["sql"]


def test_disabled_or_deleted_account_loses_access_immediately(fake_users):
    token = auth.create_token(LOJA)
    del fake_users["gerente.maia"]                 # load_user devolve None (apagada ou inativa)
    with pytest.raises(ApiError) as exc:
        auth.current_user(creds(token))
    assert exc.value.status == 401


def test_token_has_expiry_and_subject():
    payload = jwt.decode(auth.create_token(LOJA), auth.SECRET, algorithms=["HS256"])
    assert payload["sub"] == "gerente.maia"
    assert payload["exp"] - payload["iat"] == auth.TOKEN_HOURS * 3600


def _forge(payload: dict, secret: str | None = None) -> str:
    return jwt.encode(payload, secret or auth.SECRET, algorithm="HS256")


def _base(**extra) -> dict:
    now = datetime.now(UTC)
    return {**LOJA, "sub": LOJA["username"], "iat": now, "exp": now + timedelta(hours=1), **extra}


@pytest.mark.parametrize("token_factory", [
    lambda: _forge(_base(exp=datetime.now(UTC) - timedelta(seconds=1))),   # expirado
    lambda: _forge(_base(), secret="another-secret-that-is-long-enough-123456"),     # assinatura errada
    lambda: _forge({k: v for k, v in _base().items() if k != "exp"}),                # sem exp
    lambda: _forge({k: v for k, v in _base().items() if k != "sub"}),                # sem sub
    lambda: _forge(_base(sub="nao.existe")),                                         # conta inexistente
    lambda: jwt.encode(_base(role="imperador"), None, algorithm="none"),            # alg=none
    lambda: auth.create_token(LOJA) + "x",                                           # adulterado
    lambda: "isto.nao.e-um-jwt",
], ids=["expired", "wrong-secret", "no-exp", "no-sub", "unknown-user", "alg-none", "tampered", "garbage"])
def test_invalid_tokens_are_rejected(token_factory):
    with pytest.raises(ApiError) as exc:
        auth.current_user(creds(token_factory()))
    assert exc.value.status == 401


def test_cannot_escalate_by_editing_payload():
    """Mudar o perfil no payload sem a chave invalida a assinatura."""
    header, _, signature = auth.create_token(LOJA).split(".")
    payload = {**_base(role="imperador"), "iat": 0, "exp": 9_999_999_999}
    fake_payload = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    with pytest.raises(ApiError):
        auth.current_user(creds(f"{header}.{fake_payload}.{signature}"))


# ---------- Login e load_user (BD simulada) ----------

class FakeConn:
    def __init__(self, row):
        self.row = row
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=None):
        self.queries.append((sql, params))
        return self

    def fetchone(self):
        return self.row


HASH = bcrypt.hashpw(b"loja123", bcrypt.gensalt(rounds=4)).decode()
# id, username, role, brand_id, store_id, modules, password_hash, active
ROW = (3, "gerente.maia", "loja", None, 1, None, False, HASH, True)     # ..., modules, protected, hash, active


@pytest.fixture
def db(monkeypatch):
    def install(row):
        conn = FakeConn(row)
        monkeypatch.setattr(auth, "connection", lambda *a, **k: conn)
        return conn
    return install


def test_authenticate_ok(db):
    conn = db(ROW)
    assert auth.authenticate("gerente.maia", "loja123") == {
        "id": 3, "username": "gerente.maia", "role": "loja", "brand_id": None, "store_id": 1,
        "modules": ["sql", "forecast", "orders", "users"], "protected": False}
    assert "last_login" in conn.queries[-1][0]          # regista a hora do login


def test_authenticate_uses_saved_modules(db):
    db((3, "gerente.maia", "loja", None, 1, ["forecast"], False, HASH, True))
    assert auth.authenticate("gerente.maia", "loja123")["modules"] == ["forecast"]


def test_authenticate_wrong_password(db):
    db(ROW)
    assert auth.authenticate("gerente.maia", "errada") is None


def test_disabled_account_cannot_log_in_and_still_checks_a_hash(db, monkeypatch):
    db(ROW[:8] + (False,))
    checked = []
    monkeypatch.setattr(auth, "_check_password", lambda pw, h: checked.append(h) or True)
    assert auth.authenticate("gerente.maia", "loja123") is None
    assert checked == [auth._DUMMY_HASH]                # mesmo tempo que uma conta inexistente


def test_authenticate_unknown_user_still_checks_a_hash(db, monkeypatch):
    """Sem isto, um utilizador inexistente respondia mais depressa (enumeração)."""
    db(None)
    checked = []
    monkeypatch.setattr(auth, "_check_password", lambda pw, h: checked.append(h) or False)
    assert auth.authenticate("ninguem", "x") is None
    assert checked == [auth._DUMMY_HASH]


def test_authenticate_user_without_password(db):
    db(ROW[:7] + (None, True))
    assert auth.authenticate("novo", "") is None


def test_password_over_72_bytes_does_not_crash(db):
    db(ROW)
    assert auth.authenticate("gerente.maia", "ç" * 100) is None


def test_username_is_a_bound_parameter(db):
    conn = db(None)
    auth.authenticate("x' OR '1'='1", "x")
    sql, params = conn.queries[0]
    assert "%s" in sql and params == ("x' OR '1'='1",)


def test_load_user_only_returns_active_accounts(db):
    conn = db(ROW[:7])
    assert REAL_LOAD_USER("gerente.maia")["modules"] == ["sql", "forecast", "orders", "users"]
    assert "AND active" in conn.queries[0][0]
    db(None)
    assert REAL_LOAD_USER("gerente.maia") is None


def test_public_user_hides_the_internal_id():
    assert "id" not in auth.public_user(LOJA) and auth.public_user(LOJA)["modules"]
