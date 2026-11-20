"""Recuperação de password por email ("Esqueceu-se da password?").

1. ``request_reset``: recebe o email (ou o nome de utilizador). Se for de uma conta
   ativa com email, cria um token aleatório e guarda só o SHA-256 dele, válido
   ``TOKEN_MINUTES`` e de uso único (pedidos anteriores deixam de valer). Quem chama
   envia o link por email em segundo plano e responde sempre o mesmo, exista a conta
   ou não, para não revelar que emails estão registados.
2. ``reset_password``: com o token do link, grava a nova password (mesmas regras do
   perfil) e gasta o token.

As contas de demonstração (``protected``, não admin) não recuperam nem mudam a
password: ela é pública e mudá-la trancava a demo a toda a gente. Como estas contas
já são públicas, dizê-lo claramente não revela nada.
"""
import hashlib
import secrets

import bcrypt

from multistore_ai_assistant.api.auth import BUMP_TOKEN_VERSION
from multistore_ai_assistant.api.errors import ApiError
from multistore_ai_assistant.api.permissions import is_demo
from multistore_ai_assistant.api.profile import PasswordError, check_new_password
from multistore_ai_assistant.db.pool import connection

TOKEN_MINUTES = 30
TOKEN_BYTES = 32


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def request_reset(login: str, ip: str | None = None) -> dict | None:
    """Cria um token para a conta com este email/username.

    Returns:
        ``{"username", "email", "token"}`` para enviar o email, ou ``None`` se não houver
        conta ativa com email (a resposta pública é a mesma nos dois casos).

    Raises:
        ApiError ``reset_demo`` (403): conta de demonstração (pública).
    """
    login = login.strip()
    with connection("owner") as conn:
        row = conn.execute(
            """SELECT id, username, role, protected, email FROM users
               WHERE active AND (lower(email) = lower(%s) OR username = lower(%s))
               ORDER BY (lower(email) = lower(%s)) DESC LIMIT 1""",
            (login, login, login)).fetchone()
        if not row:
            return None
        user_id, username, role, protected, email = row
        if is_demo({"role": role, "protected": protected}):
            raise ApiError("reset_demo", 403)
        if not email:
            return None
        token = secrets.token_urlsafe(TOKEN_BYTES)
        conn.execute("UPDATE password_resets SET used_at = now() WHERE user_id = %s AND used_at IS NULL",
                     (user_id,))
        conn.execute(
            """INSERT INTO password_resets (user_id, token_hash, expires_at, requested_ip)
               VALUES (%s, %s, now() + make_interval(mins => %s), %s)""",
            (user_id, token_hash(token), TOKEN_MINUTES, ip))
    return {"username": username, "email": email, "token": token}


def reset_password(token: str, new_password: str) -> str:
    """Grava a nova password e gasta o token; devolve o username.

    Raises:
        ApiError ``reset_invalid`` (400): token desconhecido, expirado, já usado ou conta desativada.
        ApiError ``reset_demo`` (403): conta de demonstração.
        ApiError ``pw_*`` (400): a nova password não cumpre as regras.
    """
    with connection("owner") as conn:
        row = conn.execute(
            """SELECT r.id, u.id, u.username, u.role, u.protected
               FROM password_resets r JOIN users u ON u.id = r.user_id
               WHERE r.token_hash = %s AND r.used_at IS NULL AND r.expires_at > now() AND u.active
               FOR UPDATE OF r""",
            (token_hash(token),)).fetchone()
        if not row:
            raise ApiError("reset_invalid", 400)
        reset_id, user_id, username, role, protected = row
        if is_demo({"role": role, "protected": protected}):
            raise ApiError("reset_demo", 403)
        try:
            check_new_password(username, "", new_password)
        except PasswordError as e:
            raise ApiError(e.code, 400, str(e), **e.params) from None
        hashed = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
        conn.execute(
            f"UPDATE users SET password_hash = %s, {BUMP_TOKEN_VERSION} WHERE id = %s",   # revoga as sessões
            (hashed, user_id),
        )
        # Gasta este token e qualquer outro pendente da mesma conta
        conn.execute("UPDATE password_resets SET used_at = now() WHERE user_id = %s AND used_at IS NULL",
                     (user_id,))
    return username
