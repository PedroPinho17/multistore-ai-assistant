"""Foto de perfil: validação do data URL e endpoints (BD simulada)."""
import base64

import pytest
from fastapi.testclient import TestClient

from multistore_ai_assistant.api import auth
from multistore_ai_assistant.api import main as api
from multistore_ai_assistant.api.profile import AVATAR_MAX_CHARS, AvatarError, check_avatar
from tests.conftest import LOJA, patch_route

client = TestClient(api.app)
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 40
WEBP = b"RIFF\x24\x00\x00\x00WEBPVP8 " + b"\x00" * 40


def data_url(kind, raw):
    return f"data:image/{kind};base64," + base64.b64encode(raw).decode()


@pytest.mark.parametrize("kind,raw", [("png", PNG), ("jpeg", JPEG), ("webp", WEBP)])
def test_real_images_are_accepted(kind, raw):
    assert check_avatar(data_url(kind, raw)).startswith(f"data:image/{kind}")


@pytest.mark.parametrize("value", [
    data_url("png", b"<svg onload=alert(1)>"),                   # tipo declarado não bate com o conteúdo
    data_url("png", JPEG),
    "data:image/svg+xml;base64," + base64.b64encode(b"<svg/>").decode(),   # SVG pode ter scripts
    "data:text/html;base64," + base64.b64encode(b"<script>").decode(),
    "data:image/png;base64,@@@",
    "https://exemplo.com/foto.png",
    "javascript:alert(1)",
])
def test_fake_or_dangerous_images_are_rejected(value):
    with pytest.raises(AvatarError):
        check_avatar(value)


def test_too_big_is_rejected():
    with pytest.raises(AvatarError):
        check_avatar(data_url("png", PNG + b"\x00" * AVATAR_MAX_CHARS))


def bearer(user=LOJA):
    return {"Authorization": "Bearer " + auth.create_token(user)}


def test_upload_and_remove(monkeypatch):
    saved = []
    patch_route(monkeypatch, "set_avatar", lambda u, v: saved.append((u, v)))
    img = data_url("webp", WEBP)
    assert client.post("/profile/avatar", json={"image": img}, headers=bearer()).status_code == 200
    assert client.delete("/profile/avatar", headers=bearer()).status_code == 200
    assert saved == [("gerente.maia", img), ("gerente.maia", None)]


def test_invalid_upload_is_400_with_the_reason(monkeypatch):
    def refuse(u, v):
        raise AvatarError("avatar_not_image", "O conteúdo não é uma imagem válida.")
    patch_route(monkeypatch, "set_avatar", refuse)
    r = client.post("/profile/avatar", json={"image": "data:image/png;base64,AAAA"}, headers=bearer())
    assert r.status_code == 400 and "imagem" in r.json()["detail"]["message"]


def test_upload_needs_login_and_has_a_size_limit():
    assert client.post("/profile/avatar", json={"image": "x"}).status_code in (401, 403)
    big = {"image": "a" * (AVATAR_MAX_CHARS + 1)}
    assert client.post("/profile/avatar", json=big, headers=bearer()).status_code == 422


def test_ui_script_is_served():
    r = client.get("/static/js/ui.js")
    assert r.status_code == 200 and "LangPicker" in r.text
