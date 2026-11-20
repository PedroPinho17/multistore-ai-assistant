"""Foto de perfil: validação com Pillow, normalização (256×256 WebP sem EXIF) e endpoints (BD simulada)."""
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from multistore_ai_assistant.api import auth, avatars
from multistore_ai_assistant.api import main as api
from multistore_ai_assistant.api.avatars import AvatarError, process_image
from tests.conftest import LOJA, patch_route

client = TestClient(api.app)
NAME = "0123456789abcdef0123456789abcdef.webp"


def image_bytes(fmt="PNG", size=(300, 200), color=(200, 30, 30), mode="RGB", **save) -> bytes:
    out = BytesIO()
    Image.new(mode, size, color).save(out, fmt, **save)
    return out.getvalue()


def opened(data: bytes) -> Image.Image:
    im = Image.open(BytesIO(data))
    im.load()
    return im


def bearer(user=LOJA):
    return {"Authorization": "Bearer " + auth.create_token(user)}


def upload(data: bytes, content_type="image/png", user=LOJA, **headers):
    return client.post("/me/avatar", content=data,
                       headers={**bearer(user), "Content-Type": content_type, **headers})


@pytest.fixture
def avatar_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(avatars, "AVATAR_DIR", tmp_path)
    return tmp_path


# ---------- process_image ----------

@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP"])
def test_valid_images_become_a_256_webp(fmt):
    im = opened(process_image(image_bytes(fmt)))
    assert im.format == "WEBP" and im.size == (256, 256)


def test_non_square_images_are_center_cropped():
    raw = BytesIO()
    im = Image.new("RGB", (600, 200), (0, 0, 255))
    im.paste((255, 0, 0), (200, 0, 400, 200))                  # o terço do meio é vermelho
    im.save(raw, "PNG")
    out = opened(process_image(raw.getvalue())).convert("RGB")
    assert out.getpixel((5, 128))[0] > 200 and out.getpixel((250, 128))[0] > 200   # só sobra o meio


def test_exif_is_stripped_and_the_orientation_applied():
    raw = BytesIO()
    im = Image.new("RGB", (200, 100), (255, 0, 0))
    im.paste((0, 0, 255), (100, 0, 200, 100))                  # esquerda vermelha, direita azul
    exif = Image.Exif()
    exif[0x0112] = 6                                           # Orientation: rodar 90° no sentido do relógio
    exif[0x010F] = "Telemovel XYZ"                             # Make
    im.save(raw, "JPEG", exif=exif, quality=95)
    out = opened(process_image(raw.getvalue()))
    assert not out.info.get("exif") and not out.getexif()
    assert not out.info.get("icc_profile") and not out.info.get("xmp")
    rgb = out.convert("RGB")
    assert rgb.getpixel((128, 10))[0] > 200                    # rodada: vermelho em cima…
    assert rgb.getpixel((128, 245))[2] > 200                   # …e azul em baixo


def test_transparency_is_kept():
    out = opened(process_image(image_bytes("PNG", color=(0, 0, 0, 0), mode="RGBA")))
    assert out.mode == "RGBA" and out.getpixel((128, 128))[3] == 0


@pytest.mark.parametrize("raw", [
    b"<svg xmlns='http://www.w3.org/2000/svg' onload='alert(1)'/>",
    b"<html><script>alert(1)</script></html>",
    b"\x89PNG\r\n\x1a\n" + b"\x00" * 64,                       # só os bytes mágicos de PNG
    b"\xff\xd8\xff\xe0" + b"\x00" * 64,                        # só os bytes mágicos de JPEG
    b"",
], ids=["svg", "html", "fake-png", "fake-jpeg", "empty"])
def test_fake_images_are_rejected(raw):
    with pytest.raises(AvatarError) as e:
        process_image(raw)
    assert e.value.code == "avatar_not_image" and e.value.status == 400


def test_other_real_formats_are_rejected():
    for fmt in ("GIF", "BMP", "TIFF"):
        with pytest.raises(AvatarError) as e:
            process_image(image_bytes(fmt))
        assert e.value.code == "avatar_not_image", fmt


def test_truncated_image_is_corrupt():
    noisy = BytesIO()
    Image.effect_noise((400, 400), 80).convert("RGB").save(noisy, "PNG")   # ruído: não comprime, fica grande
    raw = noisy.getvalue()
    with pytest.raises(AvatarError) as e:
        process_image(raw[: len(raw) // 2])
    assert e.value.code == "avatar_corrupt"


def test_too_many_bytes_or_pixels_is_too_big(monkeypatch):
    with pytest.raises(AvatarError) as e:
        process_image(b"\x00" * (avatars.MAX_BYTES + 1))
    assert (e.value.code, e.value.status) == ("avatar_too_big", 413)
    monkeypatch.setattr(avatars, "MAX_PIXELS", 100)            # "bomba" de descompressão, em pequeno
    with pytest.raises(AvatarError) as e:
        process_image(image_bytes("PNG", size=(20, 20)))
    assert e.value.code == "avatar_too_big"


@pytest.mark.parametrize("ctype,ok", [
    ("image/png", True), ("image/jpeg", True), ("IMAGE/WEBP; charset=x", True),
    ("image/gif", False), ("image/svg+xml", False), ("application/json", False), (None, False),
])
def test_declared_content_type(ctype, ok):
    if ok:
        avatars.check_content_type(ctype)
    else:
        with pytest.raises(AvatarError) as e:
            avatars.check_content_type(ctype)
        assert (e.value.code, e.value.status) == ("avatar_bad_format", 415)


# ---------- nomes de ficheiro e URL ----------

def test_url_has_a_version_for_cache_busting():
    from datetime import UTC, datetime
    assert avatars.avatar_url(None, None) is None
    url = avatars.avatar_url(NAME, datetime(2026, 11, 20, tzinfo=UTC))
    assert url == f"/avatars/{NAME}?v=1795132800"


@pytest.mark.parametrize("name", ["../secret.webp", "..%2F.env", "abc.webp", NAME.replace(".webp", ".png"),
                                  NAME.upper(), NAME + ".tmp"])
def test_only_generated_names_are_served(avatar_dir, name):
    (avatar_dir / NAME).write_bytes(b"x")
    assert avatars.avatar_file(name) is None
    assert avatars.avatar_file(NAME) == avatar_dir / NAME


def test_remove_file_ignores_foreign_names(avatar_dir):
    keep = avatar_dir / "keep.webp"
    keep.write_bytes(b"x")
    avatars.remove_file("keep.webp")
    avatars.remove_file(None)
    avatars.remove_file(NAME)                                  # não existe: não faz nada
    assert keep.exists()


# ---------- endpoints ----------

def test_valid_upload_returns_the_new_url(monkeypatch):
    calls = []
    patch_route(monkeypatch, "save_avatar", lambda u, raw: calls.append((u, raw)) or f"/avatars/{NAME}?v=1")
    data = image_bytes("PNG")
    r = upload(data)
    assert r.status_code == 200 and r.json() == {"avatar_url": f"/avatars/{NAME}?v=1"}
    assert calls == [("gerente.maia", data)]


def test_upload_runs_the_real_validation(monkeypatch):
    patch_route(monkeypatch, "save_avatar", lambda u, raw: process_image(raw) and "/avatars/x")
    r = upload(b"<svg onload=alert(1)>", "image/png", **{"Accept-Language": "en"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "avatar_not_image"
    assert "PNG, JPEG or WebP" in r.json()["detail"]["message"]


def test_wrong_type_is_415_before_reading_the_file(monkeypatch):
    patch_route(monkeypatch, "save_avatar", lambda *a: pytest.fail("não devia gravar"))
    r = upload(image_bytes("GIF"), "image/gif")
    assert r.status_code == 415 and r.json()["detail"]["code"] == "avatar_bad_format"


def test_too_large_is_413(monkeypatch):
    patch_route(monkeypatch, "save_avatar", lambda *a: pytest.fail("não devia gravar"))
    r = upload(b"\x00" * (avatars.MAX_BYTES + 1), **{"Accept-Language": "fr"})
    assert r.status_code == 413 and r.json()["detail"]["code"] == "avatar_too_big"
    assert "2 Mo" in r.json()["detail"]["message"]


def test_upload_and_delete_need_login():
    assert client.post("/me/avatar", content=b"x", headers={"Content-Type": "image/png"}).status_code in (401, 403)
    assert client.delete("/me/avatar").status_code in (401, 403)


def test_demo_accounts_cannot_change_their_photo(fake_users, monkeypatch):
    fake_users["gerente.maia"]["protected"] = True
    patch_route(monkeypatch, "save_avatar", lambda *a: pytest.fail("não devia gravar"))
    patch_route(monkeypatch, "delete_avatar", lambda *a: pytest.fail("não devia apagar"))
    for r in (upload(image_bytes("PNG")), client.delete("/me/avatar", headers=bearer())):
        assert r.status_code == 403 and r.json()["detail"]["code"] == "demo_read_only"


def test_delete_goes_back_to_initials(monkeypatch):
    removed = []
    patch_route(monkeypatch, "delete_avatar", removed.append)
    r = client.delete("/me/avatar", headers=bearer())
    assert r.status_code == 200 and r.json() == {"avatar_url": None}
    assert removed == ["gerente.maia"]                         # sempre a conta do token


def test_photos_are_served_only_with_a_session(avatar_dir):
    (avatar_dir / NAME).write_bytes(process_image(image_bytes("PNG")))
    assert client.get(f"/avatars/{NAME}").status_code in (401, 403)
    r = client.get(f"/avatars/{NAME}?v=1", headers=bearer())
    assert r.status_code == 200 and r.headers["content-type"] == "image/webp"
    assert r.headers["cache-control"] == "private, max-age=31536000, immutable"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert opened(r.content).size == (256, 256)


def test_missing_or_invalid_photo_is_404(avatar_dir):
    for name in ("ffffffffffffffffffffffffffffffff.webp", "..%2F..%2Fpyproject.toml", "x.webp"):
        r = client.get(f"/avatars/{name}", headers=bearer())
        assert r.status_code == 404, name


def test_other_api_responses_are_still_not_cached():
    assert client.get("/me", headers=bearer()).headers["cache-control"] == "no-store"

