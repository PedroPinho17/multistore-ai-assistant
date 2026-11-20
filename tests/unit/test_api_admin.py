"""Endpoints novos: /me, /ratings, registo de pedidos, gestão de contas e painel admin.

A BD é simulada (ver tests/unit/conftest.py); as funções de users/admin são
substituídas por versões que só registam as chamadas.
"""
import pytest
from fastapi.testclient import TestClient

from multistore_ai_assistant.api import admin as admin_mod
from multistore_ai_assistant.api import auth
from multistore_ai_assistant.api import main as api
from multistore_ai_assistant.api import users as users_mod
from multistore_ai_assistant.api.permissions import AccessDenied
from tests.conftest import ADMIN, IMPERADOR, LOJA, MARCA, patch_route

client = TestClient(api.app)


def bearer(user=LOJA) -> dict:
    return {"Authorization": "Bearer " + auth.create_token(user)}


@pytest.fixture
def store(monkeypatch):
    msgs = []
    patch_route(monkeypatch, "owns", lambda u, c: True)
    patch_route(monkeypatch, "create_conversation", lambda u, q: 1)
    patch_route(monkeypatch, "get_history", lambda c: [])
    patch_route(monkeypatch, "add_message", lambda *a: msgs.append(a))
    return msgs


# ---------- /me e login ----------

def test_me_returns_modules_without_the_internal_id():
    r = client.get("/me", headers=bearer(MARCA))
    assert r.status_code == 200
    assert r.json() == {**{k: MARCA[k] for k in ("username", "role", "brand_id", "store_id", "modules")}, "demo": False,
                        "avatar": None, "brand_name": None,
                        "settings": {"lang": None, "theme": None, "accent": None}}


def test_login_returns_the_public_profile(monkeypatch):
    patch_route(monkeypatch, "authenticate", lambda u, p: dict(LOJA))
    body = client.post("/login", json={"username": "gerente.maia", "password": "x"}).json()
    assert "id" not in body["user"] and body["user"]["modules"] == LOJA["modules"]


# ---------- /ask grava o registo ----------

def test_ask_saves_the_request_and_returns_its_id(monkeypatch, store, fake_request_log):
    patch_route(monkeypatch, "ask", lambda q, u, lang, h, **k: {"sql": "SELECT 1", "kind": "sql", "answer": "ok"})
    r = client.post("/ask", json={"question": "Lojas?", "lang": "en"}, headers=bearer())
    assert r.json()["request_id"] == 1
    assert fake_request_log == [{"user": "gerente.maia", "question": "Lojas?", "lang": "en", "kind": "sql",
                                 "conversation_id": 1, "llm_calls": 0, "sql_attempts": 0, "error": None}]
    assert store[-1][-1] == 1                                   # a resposta guarda o request_id


def test_failed_requests_are_logged_as_exceptions(monkeypatch, store, fake_request_log):
    def boom(*a, **k):
        raise RuntimeError("Groq em baixo")
    patch_route(monkeypatch, "ask", boom)
    assert client.post("/ask", json={"question": "q"}, headers=bearer()).status_code == 503
    assert fake_request_log[0]["kind"] == "exception" and "Groq em baixo" in fake_request_log[0]["error"]
    assert store == []                                          # nada fica na conversa


def test_denied_answers_are_logged_with_their_kind(monkeypatch, store, fake_request_log):
    patch_route(monkeypatch, "ask", lambda *a, **k: {"sql": None, "kind": "denied", "answer": "sem acesso"})
    client.post("/ask", json={"question": "q"}, headers=bearer())
    assert fake_request_log[0]["kind"] == "denied"


# ---------- /ratings ----------

def test_rating_my_own_answer(monkeypatch):
    seen = []
    patch_route(monkeypatch, "rate", lambda u, rid, r: seen.append((u["username"], rid, r)) or True)
    assert client.post("/ratings", json={"request_id": 5, "rating": -1}, headers=bearer()).status_code == 200
    assert seen == [("gerente.maia", 5, -1)]


def test_rating_someone_elses_answer_is_404(monkeypatch):
    patch_route(monkeypatch, "rate", lambda u, rid, r: False)
    assert client.post("/ratings", json={"request_id": 5, "rating": 1}, headers=bearer()).status_code == 404


@pytest.mark.parametrize("rating", [2, -2, "bom", None])
def test_rating_values_are_validated(rating):
    assert client.post("/ratings", json={"request_id": 1, "rating": rating}, headers=bearer()).status_code == 422


# ---------- /feedback exige o módulo teach ----------

def test_teaching_needs_the_teach_module(fake_users):
    fake_users["pedro"]["modules"] = ["sql"]
    r = client.post("/feedback", json={"question": "q", "sql": "SELECT 1"}, headers=bearer(IMPERADOR))
    assert r.status_code == 403


# ---------- painel admin ----------

@pytest.mark.parametrize("user", [IMPERADOR, MARCA, LOJA])
def test_only_admin_sees_the_dashboard(user):
    r = client.get("/admin/metrics", headers=bearer(user))
    assert r.status_code == 403 and r.json()["detail"]["code"] == "no_module"


def test_admin_dashboard(monkeypatch):
    monkeypatch.setattr(admin_mod, "metrics", lambda days: {"days": days})
    r = client.get("/admin/metrics?days=30", headers=bearer(ADMIN))
    assert r.status_code == 200 and r.json() == {"days": 30}


@pytest.mark.parametrize("days", [0, 91, "x"])
def test_dashboard_period_is_validated(days):
    assert client.get(f"/admin/metrics?days={days}", headers=bearer(ADMIN)).status_code == 422


def test_dashboard_needs_login():
    assert client.get("/admin/metrics").status_code in (401, 403)


# ---------- gestão de contas ----------

@pytest.fixture
def users_db(monkeypatch):
    calls = []

    def record(name, result=None):
        def f(*a, **k):
            calls.append((name, a, k))
            return result
        return f
    monkeypatch.setattr(users_mod, "list_users", record("list", [{"username": "x"}]))
    monkeypatch.setattr(users_mod, "options", record("options", {"roles": ["loja"]}))
    monkeypatch.setattr(users_mod, "create_user", record("create", {"username": "novo", "role": "loja"}))
    monkeypatch.setattr(users_mod, "update_user", record("update", {"username": "novo"}))
    monkeypatch.setattr(users_mod, "delete_user", record("delete"))
    return calls


def test_users_endpoints_need_the_users_module(fake_users, users_db):
    fake_users["gerente.maia"]["modules"] = ["sql"]
    for method, path in [("get", "/users"), ("get", "/users/options"), ("delete", "/users/1")]:
        assert getattr(client, method)(path, headers=bearer()).status_code == 403
    assert users_db == []


def test_list_and_options(users_db):
    assert client.get("/users", headers=bearer(MARCA)).json() == [{"username": "x"}]
    assert client.get("/users/options", headers=bearer(MARCA)).json() == {"roles": ["loja"]}
    assert users_db[0][1][0]["username"] == "gestor.burgerlab"       # quem atua vem do token


def test_create_user_passes_the_form_and_the_actor(users_db):
    body = {"username": "novo.gerente", "password": "Segura123", "role": "loja", "store_id": 1,
            "modules": ["sql", "forecast"]}
    r = client.post("/users", json=body, headers=bearer(MARCA))
    assert r.status_code == 201
    name, args, _ = users_db[0]
    assert name == "create" and args[0]["username"] == "gestor.burgerlab"
    assert args[1:] == ("novo.gerente", "Segura123", "loja", None, 1, ["sql", "forecast"], None)


@pytest.mark.parametrize("body", [
    {"username": "ab", "password": "x", "role": "loja"},
    {"username": "novo", "password": "x", "role": "chefe"},
    {"username": "novo", "password": "x", "role": "loja", "modules": ["root"]},
    {"username": "novo", "role": "loja"},
])
def test_create_user_validates_input(users_db, body):
    assert client.post("/users", json=body, headers=bearer(MARCA)).status_code == 422
    assert users_db == []


def test_update_and_delete(users_db):
    r = client.patch("/users/7", json={"active": False, "modules": ["sql"]}, headers=bearer(MARCA))
    assert r.status_code == 200
    assert users_db[0][1][1:] == (7, ["sql"], False, None, None)
    assert client.delete("/users/7", headers=bearer(MARCA)).json() == {"ok": True}


def test_permission_errors_carry_a_code_for_the_ui(monkeypatch):
    def refuse(*a, **k):
        raise AccessDenied("role_above", "Não podes criar contas acima do teu perfil.")
    monkeypatch.setattr(users_mod, "create_user", refuse)
    r = client.post("/users", json={"username": "chefe", "password": "Segura123", "role": "imperador"},
                    headers=bearer(MARCA))
    assert r.status_code == 403
    assert r.json() == {"detail": {"code": "role_above", "message": "Não podes criar contas acima do teu perfil."}}


def test_users_endpoints_are_rate_limited(users_db):
    codes = [client.get("/users", headers=bearer(MARCA)).status_code for _ in range(31)]
    assert codes[:30] == [200] * 30 and codes[30] == 429


# ---------- ficheiros estáticos ----------

def test_static_js_is_served_with_revalidation():
    r = client.get("/static/js/admin.js")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-cache"
    assert "javascript" in r.headers["content-type"]
