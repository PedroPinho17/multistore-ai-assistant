"""Recuperação de password: rotas, email e regras (BD e SMTP simulados)."""
import hashlib
import logging
import smtplib

import pytest
from fastapi.testclient import TestClient

from multistore_ai_assistant.api import mailer
from multistore_ai_assistant.api import main as api
from multistore_ai_assistant.api.errors import ApiError
from multistore_ai_assistant.api.password_reset import TOKEN_MINUTES, token_hash
from multistore_ai_assistant.api.permissions import AccessDenied
from multistore_ai_assistant.api.routes import password as routes
from multistore_ai_assistant.api.users import normalize_email

client = TestClient(api.app)
TOKEN = "t" * 43


@pytest.fixture
def sent(monkeypatch):
    """Emails "enviados" (mailer.send simulado)."""
    out = []
    monkeypatch.setattr(mailer, "send", lambda msg: out.append(msg) or True)
    return out


def found(monkeypatch, result):
    calls = []

    def fake(login, ip=None):
        calls.append((login, ip))
        if isinstance(result, Exception):
            raise result
        return result
    monkeypatch.setattr(routes, "request_reset", fake)
    return calls


# ---------- POST /password/forgot ----------

def test_forgot_sends_a_link_for_an_existing_account(monkeypatch, sent):
    found(monkeypatch, {"username": "ana", "email": "ana@exemplo.pt", "token": TOKEN})
    monkeypatch.setenv("APP_URL", "https://app.exemplo.pt/")
    r = client.post("/password/forgot", json={"login": "ana@exemplo.pt", "lang": "en"})
    assert r.status_code == 202 and r.json() == {"ok": True}
    assert len(sent) == 1 and sent[0]["To"] == "ana@exemplo.pt"
    assert sent[0]["Subject"].startswith("Reset your password")
    assert f"https://app.exemplo.pt/reset-password#token={TOKEN}" in sent[0].get_content()


def test_forgot_answers_the_same_when_the_account_does_not_exist(monkeypatch, sent):
    """Não revela que emails estão registados: mesma resposta, nenhum email."""
    found(monkeypatch, None)
    r = client.post("/password/forgot", json={"login": "ninguem@exemplo.pt"})
    assert r.status_code == 202 and r.json() == {"ok": True}
    assert sent == []


def test_forgot_for_a_demo_account_is_refused_clearly(monkeypatch, sent):
    found(monkeypatch, ApiError("reset_demo", 403))
    r = client.post("/password/forgot", json={"login": "pedro"}, headers={"Accept-Language": "en"})
    assert r.status_code == 403 and r.json()["detail"]["code"] == "reset_demo"
    assert "Demo accounts" in r.json()["detail"]["message"]
    assert sent == []


def test_forgot_is_rate_limited_per_ip(monkeypatch, sent):
    found(monkeypatch, None)
    codes = [client.post("/password/forgot", json={"login": f"x{i}@exemplo.pt"}).status_code for i in range(6)]
    assert codes == [202] * 5 + [429]


def test_forgot_is_rate_limited_per_email(monkeypatch, sent):
    """Muitos IPs não podem inundar a caixa de correio de uma pessoa."""
    found(monkeypatch, None)
    codes = []
    for i in range(6):
        monkeypatch.setattr(routes, "client_ip", lambda request, i=i: f"10.0.0.{i}")
        codes.append(client.post("/password/forgot", json={"login": "Ana@Exemplo.pt"}).status_code)
    assert codes[-1] == 429


@pytest.mark.parametrize("body", [{}, {"login": "ab"}, {"login": "x" * 255}, {"login": "ana@x.pt", "lang": "de"}])
def test_forgot_validates_the_body(body):
    assert client.post("/password/forgot", json=body).status_code == 422


# ---------- POST /password/reset ----------

def test_reset_sets_the_new_password(monkeypatch):
    calls = []
    monkeypatch.setattr(routes, "reset_password", lambda token, new: calls.append((token, new)) or "ana")
    r = client.post("/password/reset", json={"token": TOKEN, "new_password": "NovaPass2026"})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert calls == [(TOKEN, "NovaPass2026")]


@pytest.mark.parametrize("code,status", [("reset_invalid", 400), ("reset_demo", 403), ("pw_mix", 400)])
def test_reset_errors_are_translated(monkeypatch, code, status):
    def fail(token, new):
        raise ApiError(code, status)
    monkeypatch.setattr(routes, "reset_password", fail)
    r = client.post("/password/reset", json={"token": TOKEN, "new_password": "x"}, headers={"Accept-Language": "pt"})
    assert r.status_code == status and r.json()["detail"]["code"] == code


def test_reset_is_rate_limited(monkeypatch):
    monkeypatch.setattr(routes, "reset_password", lambda token, new: (_ for _ in ()).throw(ApiError("reset_invalid")))
    codes = [client.post("/password/reset", json={"token": TOKEN, "new_password": "x"}).status_code for _ in range(11)]
    assert codes == [400] * 10 + [429]


def test_reset_rejects_short_tokens():
    assert client.post("/password/reset", json={"token": "abc", "new_password": "x"}).status_code == 422


def test_reset_page_is_served_to_the_browser():
    r = client.get("/reset-password?token=abc", headers={"Accept": "text/html"})
    assert r.status_code == 200 and '<div id="app"' in r.text


# ---------- token e email ----------

def test_only_the_sha256_of_the_token_is_stored():
    assert token_hash(TOKEN) == hashlib.sha256(TOKEN.encode()).hexdigest() and len(token_hash(TOKEN)) == 64


@pytest.mark.parametrize("raw,clean", [
    ("  Ana.Silva@Exemplo.PT ", "Ana.Silva@exemplo.pt"), ("", None), (None, None), ("   ", None),
])
def test_normalize_email(raw, clean):
    assert normalize_email(raw) == clean


@pytest.mark.parametrize("raw", ["ana", "ana@", "@exemplo.pt", "ana@exemplo", "a b@exemplo.pt", "x" * 250 + "@a.pt"])
def test_invalid_emails_are_refused(raw):
    with pytest.raises(AccessDenied) as e:
        normalize_email(raw)
    assert e.value.code == "bad_email"


@pytest.mark.parametrize("lang,subject", [("pt", "Repor a palavra-passe"), ("en", "Reset your password"),
                                          ("es", "Restablecer"), ("fr", "Réinitialiser")])
def test_reset_email_in_four_languages(lang, subject):
    msg = mailer.build_reset_email("ana@exemplo.pt", "ana", "https://x/reset-password?token=abc", TOKEN_MINUTES, lang)
    assert msg["Subject"].startswith(subject)
    body = msg.get_content()
    assert "https://x/reset-password?token=abc" in body and str(TOKEN_MINUTES) in body and "ana" in body


# ---------- SMTP ----------

class FakeSMTP:
    instances: list = []
    fail = False

    def __init__(self, host, port, timeout=None, context=None):
        self.host, self.port, self.actions = host, port, []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        self.actions.append("starttls")

    def login(self, user, password):
        self.actions.append(("login", user))

    def send_message(self, msg):
        if FakeSMTP.fail:
            raise smtplib.SMTPServerDisconnected("down")
        self.actions.append(("send", msg["To"]))


@pytest.fixture
def smtp(monkeypatch):
    FakeSMTP.instances, FakeSMTP.fail = [], False
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
    for k in ("SMTP_PORT", "SMTP_SECURITY", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SMTP_HOST", "smtp.exemplo.pt")
    return FakeSMTP


def _msg():
    return mailer.build_reset_email("ana@exemplo.pt", "ana", "https://x/reset-password?token=SEGREDO", 30)


def test_without_smtp_nothing_is_sent_and_the_link_is_not_logged(monkeypatch, caplog):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    with caplog.at_level(logging.WARNING, logger="multistore"):
        assert mailer.send(_msg()) is False
    assert "SMTP não configurado" in caplog.text and "SEGREDO" not in caplog.text


def test_starttls_with_login(smtp, monkeypatch):
    monkeypatch.setenv("SMTP_USER", "no-reply@exemplo.pt")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")
    assert mailer.send(_msg()) is True
    server = smtp.instances[0]
    assert (server.host, server.port) == ("smtp.exemplo.pt", 587)
    assert server.actions == ["starttls", ("login", "no-reply@exemplo.pt"), ("send", "ana@exemplo.pt")]


def test_ssl_uses_port_465(smtp, monkeypatch):
    monkeypatch.setenv("SMTP_SECURITY", "ssl")
    assert mailer.send(_msg()) is True
    assert smtp.instances[0].port == 465 and "starttls" not in smtp.instances[0].actions


def test_smtp_failure_is_logged_without_the_link(smtp, caplog):
    smtp.fail = True
    with caplog.at_level(logging.ERROR, logger="multistore"):
        assert mailer.send(_msg()) is False
    assert "SMTPServerDisconnected" in caplog.text and "SEGREDO" not in caplog.text


def test_sender_defaults_to_smtp_user(smtp, monkeypatch):
    monkeypatch.setenv("SMTP_USER", "no-reply@exemplo.pt")
    assert "no-reply@exemplo.pt" in _msg()["From"]
    monkeypatch.setenv("SMTP_FROM", "Multistore AI <ajuda@exemplo.pt>")
    assert _msg()["From"] == "Multistore AI <ajuda@exemplo.pt>"
