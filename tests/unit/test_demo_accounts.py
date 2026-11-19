"""Contas de demonstração (password pública): só leitura nas contas, na password e na foto."""
import pytest
from fastapi.testclient import TestClient

from multistore_ai_assistant.api import auth
from multistore_ai_assistant.api import main as api
from multistore_ai_assistant.api.permissions import AccessDenied, can_manage, check_new_account, is_demo
from tests.conftest import ADMIN, IMPERADOR, LOJA, MARCA, patch_route

client = TestClient(api.app)
DEMO_BOSS = {**IMPERADOR, "protected": True}
REAL_STORE = {"id": 50, "role": "loja", "brand_id": None, "store_id": 1, "store_brand": 1,
              "created_by": ADMIN["id"], "protected": False}


def bearer(user) -> dict:
    return {"Authorization": "Bearer " + auth.create_token(user)}


@pytest.fixture
def demo(fake_users):
    for name in (IMPERADOR["username"], MARCA["username"], LOJA["username"]):
        fake_users[name]["protected"] = True
    fake_users[ADMIN["username"]]["protected"] = True          # o admin também é protegido, mas não é demo


def test_only_public_demo_accounts_are_read_only():
    assert is_demo(DEMO_BOSS) and is_demo({**LOJA, "protected": True})
    assert not is_demo({**ADMIN, "protected": True}) and not is_demo(IMPERADOR)


def test_a_demo_imperador_cannot_touch_a_real_account():
    assert not can_manage(DEMO_BOSS, REAL_STORE)
    assert can_manage(IMPERADOR, REAL_STORE)                   # a mesma conta, não-demo, pode


def test_a_demo_account_cannot_create_accounts():
    with pytest.raises(AccessDenied) as e:
        check_new_account(DEMO_BOSS, "imperador", None, None, None, ["sql", "users"])
    assert e.value.code == "demo_read_only"


@pytest.mark.parametrize("method,path,body", [
    ("post", "/users", {"username": "visitante.x", "password": "Outra-Pass-2026!", "role": "loja", "store_id": 1}),
    ("patch", "/users/50", {"password": "Roubada-Pass-2026!"}),
    ("patch", "/users/50", {"active": False}),
    ("delete", "/users/50", None),
    ("post", "/profile/password", {"current_password": "imperador123", "new_password": "Trancada-Pass-2026!"}),
    ("delete", "/profile/avatar", None),
])
def test_demo_writes_are_refused(demo, monkeypatch, method, path, body):
    from multistore_ai_assistant.api import users as users_logic
    monkeypatch.setattr(users_logic, "connection", lambda kind="owner": pytest.fail("não devia tocar na BD"))
    patch_route(monkeypatch, "change_password", lambda *a, **k: pytest.fail("não devia mudar a password"))
    kwargs = {"json": body} if body is not None else {}
    r = getattr(client, method)(path, headers={**bearer(IMPERADOR), "Accept-Language": "en"}, **kwargs)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "demo_read_only"
    assert "read-only" in r.json()["detail"]["message"]


def test_demo_accounts_still_see_the_accounts_page(demo, monkeypatch):
    from multistore_ai_assistant.api.routes import users as users_route
    monkeypatch.setattr(users_route, "users_db", type("U", (), {"list_users": staticmethod(lambda actor: [])}))
    assert client.get("/users", headers=bearer(IMPERADOR)).status_code == 200


def test_me_tells_the_ui_it_is_a_demo_account(demo):
    assert client.get("/me", headers=bearer(IMPERADOR)).json()["demo"] is True
    assert client.get("/me", headers=bearer(ADMIN)).json()["demo"] is False
