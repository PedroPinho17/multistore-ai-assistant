"""Página de perfil: dados do utilizador, estatísticas, mudar password e apagar histórico.

Tudo filtrado pelo username do token (nunca por um id vindo do cliente).
"""
import base64
import binascii
import re

import bcrypt

from multistore_ai_assistant.api.auth import authenticate
from multistore_ai_assistant.db.pool import connection

USER_ID = "(SELECT id FROM users WHERE username = %s)"
MIN_PASSWORD = 8
MAX_PASSWORD_BYTES = 72   # limite do bcrypt


def _conn():
    """Ligação de dono (a tabela users não é acessível ao role read-only)."""
    return connection("owner")


def get_profile(user: dict) -> dict:
    """Perfil + âmbito (nome da marca / loja) + estatísticas de utilização."""
    with _conn() as conn:
        brand = store = None
        if user.get("brand_id"):
            brand = conn.execute("SELECT name FROM brands WHERE id = %s", (user["brand_id"],)).fetchone()
        if user.get("store_id"):
            store = conn.execute(
                "SELECT s.name, b.name FROM stores s JOIN brands b ON b.id = s.brand_id WHERE s.id = %s",
                (user["store_id"],)).fetchone()
        stats = conn.execute(f"""
            SELECT count(DISTINCT c.id),
                   count(m.id) FILTER (WHERE m.role = 'user'),
                   max(m.created_at),
                   min(c.created_at)
            FROM conversations c LEFT JOIN messages m ON m.conversation_id = c.id
            WHERE c.user_id = {USER_ID}""", (user["username"],)).fetchone()
        kinds = conn.execute(f"""
            SELECT coalesce(m.kind, 'error'), count(*)
            FROM messages m JOIN conversations c ON c.id = m.conversation_id
            WHERE c.user_id = {USER_ID} AND m.role = 'assistant'
            GROUP BY 1""", (user["username"],)).fetchall()
        email = conn.execute("SELECT email FROM users WHERE username = %s", (user["username"],)).fetchone()
        stores_total = conn.execute("SELECT count(*) FROM stores").fetchone()[0]
        stores_brand = (conn.execute("SELECT count(*) FROM stores WHERE brand_id = %s",
                                     (user["brand_id"],)).fetchone()[0] if user.get("brand_id") else None)
    visible = {"admin": stores_total, "imperador": stores_total, "marca": stores_brand,
               "loja": 1}.get(user["role"], 0)
    return {
        **{k: v for k, v in user.items() if k != "id"},
        "brand_name": brand[0] if brand else (store[1] if store else None),
        "store_name": store[0] if store else None,
        "visible_stores": visible,
        "email": email[0] if email else None,
        "stats": {
            "conversations": stats[0],
            "questions": stats[1],
            "last_activity": stats[2].isoformat() if stats[2] else None,
            "first_activity": stats[3].isoformat() if stats[3] else None,
            "by_kind": dict(kinds),
        },
    }


class PasswordError(ValueError):
    """Password recusada: ``code`` para traduzir (``errors.CATALOG``), mensagem em PT."""

    def __init__(self, code: str, message: str, **params):
        super().__init__(message)
        self.code, self.params = code, params


def check_new_password(username: str, current: str, new: str) -> None:
    """Regras da nova password; levanta PasswordError com o motivo."""
    if len(new) < MIN_PASSWORD:
        raise PasswordError("pw_too_short", f"A nova palavra-passe tem de ter pelo menos {MIN_PASSWORD} caracteres.",
                            n=MIN_PASSWORD)
    if len(new.encode()) > MAX_PASSWORD_BYTES:
        raise PasswordError("pw_too_long", "A nova palavra-passe é demasiado longa.")
    if new == current:
        raise PasswordError("pw_same", "A nova palavra-passe tem de ser diferente da atual.")
    if username.lower() in new.lower():
        raise PasswordError("pw_has_username", "A palavra-passe não pode conter o nome de utilizador.")
    if new.isdigit() or new.isalpha():
        raise PasswordError("pw_mix", "Usa letras e números (ou símbolos) na palavra-passe.")


def change_password(username: str, current: str, new: str) -> None:
    """Confirma a password atual e grava o novo hash bcrypt."""
    if not authenticate(username, current):
        raise PasswordError("pw_wrong_current", "A palavra-passe atual está errada.")
    check_new_password(username, current, new)
    hashed = bcrypt.hashpw(new.encode(), bcrypt.gensalt()).decode()
    with _conn() as conn:
        conn.execute("UPDATE users SET password_hash = %s WHERE username = %s", (hashed, username))


def delete_all_conversations(username: str) -> int:
    """Apaga todas as conversas do utilizador (mensagens vão em cascata)."""
    with _conn() as conn:
        cur = conn.execute(f"DELETE FROM conversations WHERE user_id = {USER_ID}", (username,))
        return cur.rowcount


# ---------- Foto de perfil ----------

AVATAR_MAX_CHARS = 100_000          # ~73 KB de imagem; a UI envia 160×160 WebP (~10 KB)
_AVATAR_RE = re.compile(r"^data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/]+={0,2})$")
_MAGIC = {
    "png": lambda b: b.startswith(b"\x89PNG\r\n\x1a\n"),
    "jpeg": lambda b: b.startswith(b"\xff\xd8\xff"),
    "webp": lambda b: b[:4] == b"RIFF" and b[8:12] == b"WEBP",
}


class AvatarError(ValueError):
    """Imagem recusada (formato, tamanho ou conteúdo não bate com o tipo declarado)."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def check_avatar(data_url: str) -> str:
    """Valida um data URL de imagem: tipo permitido, tamanho e bytes iniciais do formato.

    Não basta confiar no ``data:image/png``: os primeiros bytes têm de ser
    mesmo de PNG/JPEG/WebP, para não guardar HTML ou SVG disfarçado.
    """
    if len(data_url) > AVATAR_MAX_CHARS:
        raise AvatarError("avatar_too_big", "A imagem é demasiado grande.")
    m = _AVATAR_RE.match(data_url)
    if not m:
        raise AvatarError("avatar_bad_format", "Formato inválido: usa PNG, JPEG ou WebP.")
    try:
        raw = base64.b64decode(m.group(2), validate=True)
    except (binascii.Error, ValueError):
        raise AvatarError("avatar_corrupt", "Imagem corrompida.") from None
    if not _MAGIC[m.group(1)](raw):
        raise AvatarError("avatar_not_image", "O conteúdo não é uma imagem válida.")
    return data_url


def set_avatar(username: str, data_url: str | None) -> None:
    """Grava (ou apaga, com ``None``) a foto de perfil da própria conta."""
    value = check_avatar(data_url) if data_url is not None else None
    with _conn() as conn:
        conn.execute("UPDATE users SET avatar = %s WHERE username = %s", (value, username))


def me_details(user: dict) -> dict:
    """Foto e nome da marca da conta (para o avatar: sem foto, mostra o logótipo da marca)."""
    with _conn() as conn:
        row = conn.execute(
            """SELECT u.avatar, coalesce(b.name, sb.name)
               FROM users u
               LEFT JOIN brands b ON b.id = u.brand_id
               LEFT JOIN stores s ON s.id = u.store_id
               LEFT JOIN brands sb ON sb.id = s.brand_id
               WHERE u.username = %s""", (user["username"],)).fetchone()
    return {"avatar": row[0], "brand_name": row[1]} if row else {"avatar": None, "brand_name": None}
