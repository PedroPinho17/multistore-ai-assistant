"""Fotos de perfil: validação com Pillow, ficheiro WebP 256×256 e URL com ``?v=``.

- Aceita PNG, JPEG e WebP até 2 MB. O conteúdo é aberto pelo Pillow (só com esses
  três descodificadores): um ficheiro com outra coisa lá dentro é recusado, seja qual
  for a extensão ou o ``Content-Type``.
- A imagem é sempre redesenhada: roda conforme o EXIF, recorta ao centro para
  256×256 e grava-se como WebP **sem metadados** (EXIF, GPS, perfil ICC).
- O ficheiro chama-se ``<uuid>.webp`` e fica em ``AVATAR_DIR`` (um volume no Docker);
  a BD guarda só esse nome em ``users.avatar_path``. A foto anterior é apagada.
- Sem foto, a UI mostra as iniciais num círculo de cor fixa por conta.
"""
import os
import re
import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from multistore_ai_assistant.db.pool import connection

AVATAR_DIR = Path(os.getenv("AVATAR_DIR") or Path(__file__).resolve().parents[3] / "data" / "avatars")
MAX_BYTES = 2 * 1024 * 1024               # tamanho máximo do ficheiro enviado
MAX_PIXELS = 40_000_000                   # p.ex. 8000×5000; trava "bombas" de descompressão
SIZE = 256                                # lado do quadrado guardado
CONTENT_TYPES = ("image/png", "image/jpeg", "image/webp")
FORMATS = ("PNG", "JPEG", "WEBP")         # os únicos descodificadores que o Pillow pode usar
FILE_RE = re.compile(r"^[0-9a-f]{32}\.webp$")


class AvatarError(ValueError):
    """Imagem recusada: ``code`` para traduzir (``errors.CATALOG``), estado HTTP e mensagem em PT."""

    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.status = code, status


def too_big() -> AvatarError:
    return AvatarError("avatar_too_big", "A imagem tem mais de 2 MB.", 413)


def check_content_type(content_type: str | None) -> None:
    """Recusa logo um tipo declarado que não é PNG/JPEG/WebP (o conteúdo é verificado depois)."""
    if (content_type or "").split(";")[0].strip().lower() not in CONTENT_TYPES:
        raise AvatarError("avatar_bad_format", "Formato inválido: usa PNG, JPEG ou WebP.", 415)


def process_image(raw: bytes) -> bytes:
    """Valida e normaliza a imagem: devolve um WebP 256×256 sem metadados."""
    if len(raw) > MAX_BYTES:
        raise too_big()
    try:
        with Image.open(BytesIO(raw), formats=FORMATS) as im:
            if im.width * im.height > MAX_PIXELS:
                raise too_big()
            im.draft("RGB", (SIZE * 2, SIZE * 2))      # JPEG: descodifica já reduzida (mais rápido, menos memória)
            im.load()                                   # descodifica tudo: ficheiro truncado ou corrompido falha aqui
            im = ImageOps.exif_transpose(im)            # fotos de telemóvel: aplica a rotação antes de largar o EXIF
            alpha = im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info
            im = ImageOps.fit(im.convert("RGBA" if alpha else "RGB"), (SIZE, SIZE), Image.Resampling.LANCZOS)
    except AvatarError:                         # é um ValueError: não o confundir com imagem corrompida
        raise
    except UnidentifiedImageError:
        raise AvatarError("avatar_not_image", "O ficheiro não é uma imagem PNG, JPEG ou WebP válida.") from None
    except (OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        raise AvatarError("avatar_corrupt", "Imagem corrompida.") from None
    # Imagem nova só com os píxeis: nenhum metadado (EXIF, XMP, ICC) passa para o ficheiro
    clean = Image.frombytes(im.mode, im.size, im.tobytes())
    out = BytesIO()
    clean.save(out, "WEBP", quality=85, method=6)
    return out.getvalue()


def avatar_url(path: str | None, updated_at: datetime | None) -> str | None:
    """URL da foto com ``?v=`` (muda a cada alteração: o browser não mostra a antiga)."""
    if not path:
        return None
    version = int(updated_at.timestamp()) if updated_at else 0
    return f"/avatars/{path}?v={version}"


def avatar_file(name: str) -> Path | None:
    """Ficheiro de uma foto, ou ``None`` se o nome não for um dos gerados ou já não existir."""
    if not FILE_RE.match(name):
        return None
    path = AVATAR_DIR / name
    return path if path.is_file() else None


def remove_file(name: str | None) -> None:
    """Apaga o ficheiro de uma foto (não faz nada se não existir)."""
    if name and FILE_RE.match(name):
        (AVATAR_DIR / name).unlink(missing_ok=True)


def save_avatar(username: str, raw: bytes) -> str:
    """Valida, grava a foto da própria conta, apaga a anterior e devolve a URL nova."""
    data = process_image(raw)
    name = f"{uuid.uuid4().hex}.webp"
    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    tmp = AVATAR_DIR / f"{name}.tmp"
    tmp.write_bytes(data)
    tmp.replace(AVATAR_DIR / name)                  # nunca fica um ficheiro a meio com o nome final
    try:
        with connection("owner") as conn:
            row = conn.execute("SELECT avatar_path FROM users WHERE username = %s FOR UPDATE",
                               (username,)).fetchone()
            updated = conn.execute(
                "UPDATE users SET avatar_path = %s, avatar_updated_at = now() WHERE username = %s "
                "RETURNING avatar_updated_at", (name, username)).fetchone()
    except BaseException:
        remove_file(name)
        raise
    if not row or not updated:                      # a conta desapareceu entretanto
        remove_file(name)
        raise AvatarError("not_found", "Utilizador não encontrado.", 404)
    remove_file(row[0])
    return avatar_url(name, updated[0])


def delete_avatar(username: str) -> None:
    """Tira a foto da própria conta (a UI volta às iniciais) e apaga o ficheiro."""
    with connection("owner") as conn:
        row = conn.execute("SELECT avatar_path FROM users WHERE username = %s FOR UPDATE", (username,)).fetchone()
        conn.execute("UPDATE users SET avatar_path = NULL, avatar_updated_at = now() WHERE username = %s",
                     (username,))
    remove_file(row[0] if row else None)
