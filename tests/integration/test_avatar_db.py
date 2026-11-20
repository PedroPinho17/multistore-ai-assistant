"""Foto de perfil de ponta a ponta: API + BD real + ficheiros (numa pasta temporária).

Usa uma conta temporária ``pytest.avatar`` (apagada no fim); as contas de demo só são
usadas para confirmar que recebem 403 e que nada muda.
"""
import os
from io import BytesIO

import bcrypt
import psycopg
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from multistore_ai_assistant.api import auth, avatars
from multistore_ai_assistant.api import main as api
from multistore_ai_assistant.api.auth import load_user

pytestmark = pytest.mark.integration
TMP = "pytest.avatar"

try:
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=3) as _c:
        _ok = _c.execute("""SELECT EXISTS (SELECT FROM information_schema.columns
                            WHERE table_name = 'users' AND column_name = 'avatar_path')""").fetchone()[0]
except Exception:
    _ok = False
if not _ok:
    pytest.skip("Base de dados indisponível ou sem a migração V012__avatar_files.sql", allow_module_level=True)

client = TestClient(api.app)


def owner():
    return psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)


def png(size=(320, 240), color=(30, 160, 90)) -> bytes:
    out = BytesIO()
    Image.new("RGB", size, color).save(out, "PNG")
    return out.getvalue()


def headers(username: str, content_type: str | None = "image/png") -> dict:
    h = {"Authorization": "Bearer " + auth.create_token(load_user(username))}
    return {**h, "Content-Type": content_type} if content_type else h


def db_path(username: str):
    with owner() as c:
        return c.execute("SELECT avatar_path FROM users WHERE username = %s", (username,)).fetchone()[0]


@pytest.fixture
def avatar_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(avatars, "AVATAR_DIR", tmp_path / "avatars")     # ainda não existe: a app cria-a
    return tmp_path / "avatars"


@pytest.fixture
def tmp_user():
    with owner() as c:
        store_id = c.execute("SELECT id FROM stores ORDER BY id LIMIT 1").fetchone()[0]
        c.execute("DELETE FROM users WHERE username = %s", (TMP,))
        c.execute("INSERT INTO users (username, password_hash, role, store_id) VALUES (%s, %s, 'loja', %s)",
                  (TMP, bcrypt.hashpw(b"Inicial2026", bcrypt.gensalt(rounds=4)).decode(), store_id))
    yield TMP
    with owner() as c:
        c.execute("DELETE FROM users WHERE username = %s", (TMP,))


def test_valid_upload_is_stored_served_and_listed(avatar_dir, tmp_user):
    r = client.post("/me/avatar", content=png(), headers=headers(tmp_user))
    assert r.status_code == 200
    url = r.json()["avatar_url"]
    name = db_path(tmp_user)
    assert url.startswith(f"/avatars/{name}?v=") and avatars.FILE_RE.match(name)
    assert [p.name for p in avatar_dir.iterdir()] == [name]                       # sem ficheiros .tmp
    stored = Image.open(avatar_dir / name)
    assert stored.format == "WEBP" and stored.size == (256, 256)

    assert client.get("/me", headers=headers(tmp_user, None)).json()["avatar_url"] == url       # barra lateral e perfil
    listed = client.get("/users", headers=headers(tmp_user, None)).json()                       # contas
    assert next(u for u in listed if u["is_me"])["avatar_url"] == url

    served = client.get(url, headers=headers(tmp_user, None))
    assert served.status_code == 200 and served.content == (avatar_dir / name).read_bytes()
    assert client.get(url).status_code in (401, 403)                                            # sem sessão


def test_a_new_photo_replaces_the_old_file_and_changes_the_url(avatar_dir, tmp_user):
    first = client.post("/me/avatar", content=png(color=(255, 0, 0)), headers=headers(tmp_user)).json()["avatar_url"]
    old = db_path(tmp_user)
    second = client.post("/me/avatar", content=png(color=(0, 0, 255)), headers=headers(tmp_user)).json()["avatar_url"]
    assert second != first and db_path(tmp_user) != old
    assert [p.name for p in avatar_dir.iterdir()] == [db_path(tmp_user)]          # a antiga foi apagada


@pytest.mark.parametrize("data,ctype,status,code", [
    (b"\x00" * (avatars.MAX_BYTES + 1), "image/png", 413, "avatar_too_big"),
    (png(), "image/gif", 415, "avatar_bad_format"),
    (b"\x89PNG\r\n\x1a\n<script>alert(1)</script>", "image/png", 400, "avatar_not_image"),
], ids=["too-large", "wrong-type", "fake-image"])
def test_bad_uploads_change_nothing(avatar_dir, tmp_user, data, ctype, status, code):
    good = client.post("/me/avatar", content=png(), headers=headers(tmp_user)).json()["avatar_url"]
    before = db_path(tmp_user)
    r = client.post("/me/avatar", content=data, headers=headers(tmp_user, ctype))
    assert r.status_code == status and r.json()["detail"]["code"] == code
    assert db_path(tmp_user) == before and [p.name for p in avatar_dir.iterdir()] == [before]
    assert client.get("/me", headers=headers(tmp_user, None)).json()["avatar_url"] == good


def test_delete_goes_back_to_initials(avatar_dir, tmp_user):
    client.post("/me/avatar", content=png(), headers=headers(tmp_user))
    url = client.get("/me", headers=headers(tmp_user, None)).json()["avatar_url"]
    r = client.delete("/me/avatar", headers=headers(tmp_user, None))
    assert r.status_code == 200 and r.json() == {"avatar_url": None}
    assert db_path(tmp_user) is None and list(avatar_dir.iterdir()) == []
    assert client.get("/me", headers=headers(tmp_user, None)).json()["avatar_url"] is None
    assert client.get(url, headers=headers(tmp_user, None)).status_code == 404
    assert client.delete("/me/avatar", headers=headers(tmp_user, None)).status_code == 200   # sem foto: não falha


@pytest.mark.parametrize("demo", ["pedro", "gestor.burgerlab", "gerente.maia"])
def test_demo_accounts_get_403(avatar_dir, demo):
    if not load_user(demo):
        pytest.skip(f"conta de demo {demo} em falta (corre set_passwords)")
    before = db_path(demo)
    for r in (client.post("/me/avatar", content=png(), headers=headers(demo)),
              client.delete("/me/avatar", headers=headers(demo, None))):
        assert r.status_code == 403 and r.json()["detail"]["code"] == "demo_read_only"
    assert db_path(demo) == before and not avatar_dir.exists()
