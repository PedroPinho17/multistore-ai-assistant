"""Perfil: regras da nova password e endpoints /profile (BD simulada)."""
import jwt
import pytest
from fastapi.testclient import TestClient

from multistore_ai_assistant.api import auth, profile
from multistore_ai_assistant.api import main as api
from multistore_ai_assistant.api.profile import PasswordError, check_new_password
from tests.conftest import IMPERADOR, LOJA, patch_route

client = TestClient(api.app)


def bearer(user=LOJA) -> dict:
    return {"Authorization": "Bearer " + auth.create_token(user)}


# ---------- regras da password ----------

@pytest.mark.parametrize("new", ["Seguro2026!", "outra-pass-9", "Ação2026x", "12345abc"])
def test_good_passwords(new):
    check_new_password("gerente.maia", "loja123", new)


@pytest.mark.parametrize("new,why", [
    ("abc12", "pelo menos 8"),                    # curta
    ("ç" * 37 + "1", "demasiado longa"),          # > 72 bytes (limite do bcrypt)
])
def test_length_rules(new, why):
    with pytest.raises(PasswordError, match=why):
        check_new_password("gerente.maia", "loja123", new)


def test_new_password_must_differ():
    with pytest.raises(PasswordError, match="diferente"):
        check_new_password("gerente.maia", "Atual2026x", "Atual2026x")


@pytest.mark.parametrize("new,why", [
    ("xxgerente.maiaxx1", "nome de utilizador"),
    ("XXGERENTE.MAIA99", "nome de utilizador"),
    ("12345678", "letras e números"),
    ("abcdefgh", "letras e números"),
    ("ÁçãõÉêíó", "letras e números"),
])
def test_rejected_passwords(new, why):
    with pytest.raises(PasswordError, match=why):
        check_new_password("gerente.maia", "loja123", new)


def test_change_password_requires_the_current_one(monkeypatch):
    monkeypatch.setattr(profile, "authenticate", lambda u, p: None)
    monkeypatch.setattr(profile, "_conn", lambda: pytest.fail("não devia gravar"))
    with pytest.raises(PasswordError, match="atual está errada"):
        profile.change_password("gerente.maia", "errada", "NovaPass2026")


def test_change_password_stores_a_bcrypt_hash_and_bumps_the_version(monkeypatch):
    saved = []

    class Conn:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, sql, params):
            saved.append((sql, params))
            return self
        def fetchone(self):
            return (4,)

    monkeypatch.setattr(profile, "authenticate", lambda u, p: {"username": u})
    monkeypatch.setattr(profile, "_conn", Conn)
    assert profile.change_password("gerente.maia", "loja123", "NovaPass2026") == 4
    sql, (hashed, user) = saved[0]
    assert "token_version = token_version + 1" in sql and user == "gerente.maia"
    assert "RETURNING token_version" in sql
    assert hashed.startswith("$2") and "NovaPass2026" not in hashed
    assert auth.bcrypt.checkpw(b"NovaPass2026", hashed.encode())


# ---------- endpoints ----------

def test_profile_requires_login():
    assert client.get("/profile").status_code in (401, 403)


def test_profile_returns_data_for_the_token_user(monkeypatch):
    seen = []
    patch_route(monkeypatch, "get_profile", lambda u: seen.append(u) or {**u, "stats": {}})
    r = client.get("/profile", headers=bearer(LOJA))
    assert r.status_code == 200 and seen[0]["username"] == "gerente.maia"


def test_change_password_ok_returns_a_token_with_the_new_version(monkeypatch, fake_users):
    calls = []

    def change(*a):
        calls.append(a)
        fake_users["gerente.maia"]["token_version"] = 1     # o que o UPDATE faz na BD
        return 1
    patch_route(monkeypatch, "change_password", change)
    old = auth.create_token(LOJA)
    r = client.post("/profile/password", headers={"Authorization": "Bearer " + old},
                    json={"current_password": "loja123", "new_password": "NovaPass2026"})
    assert r.status_code == 200 and calls == [("gerente.maia", "loja123", "NovaPass2026")]
    fresh = r.json()["token"]
    assert jwt.decode(fresh, auth.SECRET, algorithms=["HS256"])["tv"] == 1
    assert client.get("/me", headers={"Authorization": "Bearer " + fresh}).status_code == 200
    assert client.get("/me", headers={"Authorization": "Bearer " + old}).status_code == 401


def test_change_password_when_the_account_vanished_is_401(monkeypatch):
    patch_route(monkeypatch, "change_password", lambda *a: None)
    r = client.post("/profile/password", headers=bearer(LOJA),
                    json={"current_password": "loja123", "new_password": "NovaPass2026"})
    assert r.status_code == 401


def test_wrong_current_password_is_400_not_401(monkeypatch):
    """401 faria a UI terminar a sessão; uma password mal escrita não deve expulsar ninguém."""
    def wrong(*a):
        raise PasswordError("pw_wrong_current", "A palavra-passe atual está errada.")
    patch_route(monkeypatch, "change_password", wrong)
    r = client.post("/profile/password", headers=bearer(),
                    json={"current_password": "x", "new_password": "NovaPass2026"})
    assert r.status_code == 400 and r.json()["detail"]["message"].startswith("A palavra-passe atual")


def test_password_changes_are_rate_limited(monkeypatch):
    def wrong(*a):
        raise PasswordError("pw_wrong_current", "A palavra-passe atual está errada.")
    patch_route(monkeypatch, "change_password", wrong)
    body = {"current_password": "x", "new_password": "NovaPass2026"}
    codes = [client.post("/profile/password", headers=bearer(), json=body).status_code for _ in range(6)]
    assert codes == [400] * 5 + [429]


@pytest.mark.parametrize("body", [{}, {"current_password": "", "new_password": "x"},
                                  {"current_password": "x", "new_password": "y" * 129}])
def test_password_input_validation(body):
    assert client.post("/profile/password", headers=bearer(), json=body).status_code == 422


def test_delete_all_conversations_only_mine(monkeypatch):
    seen = []
    patch_route(monkeypatch, "delete_all_conversations", lambda u: seen.append(u) or 3)
    r = client.delete("/conversations", headers=bearer(IMPERADOR))
    assert r.json() == {"deleted": 3} and seen == ["pedro"]
