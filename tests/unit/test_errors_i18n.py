"""Erros da API: um só formato e a língua do pedido (Accept-Language)."""
import pytest
from fastapi.testclient import TestClient

from multistore_ai_assistant.api import auth
from multistore_ai_assistant.api import main as api
from multistore_ai_assistant.api.errors import CATALOG, LANGS, ApiError, request_lang, tr
from tests.conftest import LOJA, patch_route

client = TestClient(api.app)


def test_every_message_exists_in_the_four_languages():
    for code, texts in CATALOG.items():
        assert set(texts) == set(LANGS), code
        assert all(t.strip() for t in texts.values()), code


@pytest.mark.parametrize("header,lang", [("en-GB,en;q=0.9", "en"), ("es", "es"), ("fr-FR", "fr"),
                                         ("de-DE,pt;q=0.5", "pt"), ("", "pt"), ("xx", "pt")])
def test_request_language_comes_from_accept_language(header, lang):
    class Req:
        headers = {"accept-language": header}
    assert request_lang(Req()) == lang


@pytest.mark.parametrize("lang,text", [("pt", "errados"), ("en", "Wrong username"), ("es", "incorrectos"),
                                       ("fr", "incorrect")])
def test_login_error_follows_the_language(monkeypatch, lang, text):
    patch_route(monkeypatch, "authenticate", lambda u, p: None)
    r = client.post("/login", json={"username": "x", "password": "y"}, headers={"Accept-Language": lang})
    assert r.status_code == 401 and r.json()["detail"]["code"] == "bad_login"
    assert text in r.json()["detail"]["message"]


def test_parameters_are_filled_in():
    assert tr("pw_too_short", "en", n=8) == "The password must have at least 8 characters."
    assert tr("no_module", "fr", module="sql") == "Ton compte n'a pas le module « sql »."


def test_unknown_codes_fall_back_to_the_message():
    assert ApiError("algo_novo", 400, "texto livre").message == "texto livre"
    assert tr("algo_novo") == "algo_novo"


def test_session_errors_are_translated_too():
    r = client.get("/me", headers={"Authorization": "Bearer lixo", "Accept-Language": "es"})
    assert r.status_code == 401
    assert r.json()["detail"] == {"code": "session_invalid", "message": "Sesión no válida o caducada."}


def test_rate_limit_keeps_retry_after_and_is_translated(monkeypatch):
    patch_route(monkeypatch, "authenticate", lambda u, p: None)
    for _ in range(10):
        client.post("/login", json={"username": "x", "password": "y"})
    r = client.post("/login", json={"username": "x", "password": "y"}, headers={"Accept-Language": "en"})
    assert r.status_code == 429 and r.headers["retry-after"]
    assert r.json()["detail"]["message"].startswith("Too many requests")


def test_password_rules_come_back_with_their_code(monkeypatch):
    from multistore_ai_assistant.api.profile import PasswordError

    def refuse(*a):
        raise PasswordError("pw_too_short", "curta", n=8)
    patch_route(monkeypatch, "change_password", refuse)
    token = auth.create_token(LOJA)
    r = client.post("/profile/password", json={"current_password": "a", "new_password": "b"},
                    headers={"Authorization": "Bearer " + token, "Accept-Language": "fr"})
    assert r.json()["detail"] == {"code": "pw_too_short",
                                  "message": "Le mot de passe doit avoir au moins 8 caractères."}
