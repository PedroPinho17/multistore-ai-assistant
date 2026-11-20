"""Página de perfil: dados do utilizador, estatísticas, mudar password e apagar histórico.

Tudo filtrado pelo username do token (nunca por um id vindo do cliente).
"""
import bcrypt

from multistore_ai_assistant.api.auth import BUMP_TOKEN_VERSION, authenticate
from multistore_ai_assistant.api.avatars import avatar_url
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
        **{k: v for k, v in user.items() if k not in ("id", "token_version")},
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


def change_password(username: str, current: str, new: str) -> int | None:
    """Confirma a password atual, grava o novo hash bcrypt e revoga as sessões abertas.

    Returns:
        A nova ``token_version`` (para emitir o token de quem mudou), ou ``None``
        se a conta desapareceu entretanto.
    """
    if not authenticate(username, current):
        raise PasswordError("pw_wrong_current", "A palavra-passe atual está errada.")
    check_new_password(username, current, new)
    hashed = bcrypt.hashpw(new.encode(), bcrypt.gensalt()).decode()
    with _conn() as conn:
        row = conn.execute(
            f"UPDATE users SET password_hash = %s, {BUMP_TOKEN_VERSION} "
            "WHERE username = %s RETURNING token_version",
            (hashed, username),
        ).fetchone()
    return row[0] if row else None


def delete_all_conversations(username: str) -> int:
    """Apaga todas as conversas do utilizador (mensagens vão em cascata)."""
    with _conn() as conn:
        cur = conn.execute(f"DELETE FROM conversations WHERE user_id = {USER_ID}", (username,))
        return cur.rowcount


# ---------- Foto de perfil (a gravação está em ``avatars``) ----------

def me_details(user: dict) -> dict:
    """URL da foto (``None`` = a UI mostra as iniciais) e nome da marca da conta."""
    with _conn() as conn:
        row = conn.execute(
            """SELECT u.avatar_path, u.avatar_updated_at, coalesce(b.name, sb.name)
               FROM users u
               LEFT JOIN brands b ON b.id = u.brand_id
               LEFT JOIN stores s ON s.id = u.store_id
               LEFT JOIN brands sb ON sb.id = s.brand_id
               WHERE u.username = %s""", (user["username"],)).fetchone()
    if not row:
        return {"avatar_url": None, "brand_name": None}
    return {"avatar_url": avatar_url(row[0], row[1]), "brand_name": row[2]}
