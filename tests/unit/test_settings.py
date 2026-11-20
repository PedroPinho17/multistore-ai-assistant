"""Definições da conta e da aplicação (validação e endpoints, BD simulada)."""
import jwt
import pytest
from fastapi.testclient import TestClient

from multistore_ai_assistant.api import auth
from multistore_ai_assistant.api import main as api
from multistore_ai_assistant.api import settings as st
from tests.conftest import ADMIN, IMPERADOR, LOJA

client = TestClient(api.app)


def bearer(user=LOJA):
    return {"Authorization": "Bearer " + auth.create_token(user)}


# ---------- validação ----------

def test_user_changes_accept_known_values_and_null():
    assert st.check_user_changes({"lang": "fr", "theme": "system", "accent": "wine"}) == \
        {"lang": "fr", "theme": "system", "accent": "wine"}
    assert st.check_user_changes({"accent": None}) == {"accent": None}


@pytest.mark.parametrize("changes", [{"lang": "de"}, {"theme": "sepia"}, {"accent": "#fff"}, {"accent": "red"},
                                     {"accent": "#gggggg"}, {"accent": "#ff0000; x"}, {"font": "x"}])
def test_user_changes_reject_unknown(changes):
    with pytest.raises(st.SettingsError) as e:
        st.check_user_changes(changes)
    assert e.value.code == "bad_setting" and e.value.status == 400


@pytest.mark.parametrize("changes", [
    {"session_hours": 3}, {"session_hours": True}, {"session_hours": "8"},
    {"show_demo_accounts": "sim"}, {"default_accent": "pink"}, {"default_lang": "it"}, {"theme": "dark"},
])
def test_app_changes_reject_invalid(changes):
    with pytest.raises(st.SettingsError):
        st.check_app_changes(changes)


@pytest.mark.parametrize("raw,saved", [("#ff8800", "#ff8800"), ("#0F7A5A", "#0f7a5a")])
def test_custom_hex_colors_are_accepted_and_lowercased(raw, saved):
    assert st.check_user_changes({"accent": raw}) == {"accent": saved}
    assert st.check_app_changes({"default_accent": raw}) == {"default_accent": saved}


def test_custom_color_through_the_api(monkeypatch):
    seen = []
    monkeypatch.setattr(st, "update_user_settings", lambda u, c: seen.append(c) or {})
    assert client.put("/settings/me", json={"accent": "#C2185B"}, headers=bearer()).status_code == 200
    assert client.put("/settings/me", json={"accent": "#c2185"}, headers=bearer()).status_code == 422
    assert seen == [{"accent": "#C2185B"}]          # a API aceita; check_user_changes normaliza


def test_app_changes_accept_valid():
    ok = {"session_hours": 12, "show_demo_accounts": False, "default_accent": "blue", "default_lang": "en"}
    assert st.check_app_changes(ok) == ok


def test_only_admin_can_update_app_settings():
    with pytest.raises(st.AccessDenied) as e:
        st.update_app_settings(IMPERADOR, {"session_hours": 4})
    assert e.value.code == "admin_only"


def test_every_accent_has_css_and_favicon_colors():
    """Cada cor da lista fechada tem de existir na UI (CSS e favicon)."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    css = "".join(p.read_text(encoding="utf-8") for p in (root / "frontend" / "src" / "styles").glob("*.css"))
    accent_ts = (root / "frontend" / "src" / "lib" / "accent.ts").read_text(encoding="utf-8")
    for accent in st.ACCENTS:
        assert f'[data-accent="{accent}"]' in css and f"{accent}:" in accent_ts



# ---------- endpoints ----------

def test_public_config_needs_no_login(fake_settings):
    fake_settings["show_demo_accounts"] = False
    r = client.get("/config")
    assert r.status_code == 200
    assert r.json() == {"default_accent": "green", "default_lang": "pt", "show_demo_accounts": False}
    assert "session_hours" not in r.json()


def test_save_my_settings(monkeypatch):
    seen = []
    monkeypatch.setattr(st, "update_user_settings",
                        lambda u, c: seen.append((u["username"], c)) or {"lang": None, "theme": "dark", "accent": None})
    r = client.put("/settings/me", json={"theme": "dark"}, headers=bearer())
    assert r.status_code == 200 and seen == [("gerente.maia", {"theme": "dark"})]
    client.put("/settings/me", json={"accent": None}, headers=bearer())
    assert seen[-1][1] == {"accent": None}                 # null = voltar à predefinição


@pytest.mark.parametrize("body", [{"theme": "sepia"}, {"accent": "pink"}, {"lang": "de"}, {"role": "admin"}])
def test_my_settings_are_validated(body):
    assert client.put("/settings/me", json=body, headers=bearer()).status_code == 422


def test_my_settings_need_login():
    assert client.put("/settings/me", json={"theme": "dark"}).status_code in (401, 403)


@pytest.mark.parametrize("user", [IMPERADOR, LOJA])
def test_app_settings_are_admin_only(user):
    assert client.get("/settings/app", headers=bearer(user)).status_code == 403
    r = client.put("/settings/app", json={"session_hours": 4}, headers=bearer(user))
    assert r.status_code == 403 and r.json()["detail"]["code"] == "admin_only"


def test_admin_updates_app_settings(monkeypatch):
    seen = []
    monkeypatch.setattr(st, "update_app_settings", lambda u, c: seen.append(c) or {"values": c})
    r = client.put("/settings/app", json={"session_hours": 12, "show_demo_accounts": False}, headers=bearer(ADMIN))
    assert r.status_code == 200 and seen == [{"session_hours": 12, "show_demo_accounts": False}]


@pytest.mark.parametrize("body", [{"session_hours": 5}, {"default_accent": "pink"}, {"nope": 1}])
def test_app_settings_are_validated(body):
    assert client.put("/settings/app", json=body, headers=bearer(ADMIN)).status_code == 422


# ---------- duração da sessão ----------

def test_session_length_follows_the_app_setting(fake_settings):
    fake_settings["session_hours"] = 2
    payload = jwt.decode(auth.create_token(LOJA), auth.SECRET, algorithms=["HS256"])
    assert payload["exp"] - payload["iat"] == 2 * 3600


def test_settings_fall_back_to_defaults_when_the_db_is_down(monkeypatch):
    monkeypatch.undo()                                     # tira a versão simulada desta função
    st.clear_cache()

    def broken(*a, **k):
        raise RuntimeError("BD em baixo")
    monkeypatch.setattr(st, "connection", broken)
    assert st.get_app_settings() == st.APP_DEFAULTS
    st.clear_cache()


# ---------- favicon e manifesto ----------

def test_favicon_and_manifest_are_served():
    ico = client.get("/favicon.ico")
    assert ico.status_code == 200 and ico.headers["content-type"] == "image/x-icon"
    svg = client.get("/icons/favicon.svg")
    assert svg.status_code == 200 and "svg" in svg.headers["content-type"]
    manifest = client.get("/site.webmanifest")
    assert manifest.status_code == 200 and "manifest+json" in manifest.headers["content-type"]
    icons = manifest.json()["icons"]
    for icon in icons:
        assert client.get(icon["src"]).status_code == 200, icon["src"]
