"""Cria a conta ``admin`` (só para o dono da aplicação; nunca é uma conta de demo).

O admin vê os dados como o Imperador e tem, além disso, o painel de
observabilidade e a gestão de todas as contas.

Uso:
    python -m multistore_ai_assistant.data.create_admin <username>        # pede a password
    python -m multistore_ai_assistant.data.create_admin                   # usa ADMIN_USERNAME / ADMIN_PASSWORD do .env

Se a conta já existir, a password só muda com ``--reset-password``.
Recusa transformar as contas de demonstração (ou outra conta qualquer) em admin.
"""
import getpass
import os
import sys

import bcrypt
import psycopg
from dotenv import load_dotenv

from multistore_ai_assistant.api.users import USERNAME_RE

load_dotenv()
MIN_ADMIN_PASSWORD = 12


def check_admin_password(username: str, password: str) -> str | None:
    """Motivo pelo qual a password não serve, ou ``None`` se estiver boa."""
    if len(password) < MIN_ADMIN_PASSWORD:
        return f"A password do admin tem de ter pelo menos {MIN_ADMIN_PASSWORD} caracteres."
    if len(password.encode()) > 72:
        return "A password é demasiado longa (máximo 72 bytes)."
    if username.lower() in password.lower():
        return "A password não pode conter o nome de utilizador."
    if password.isdigit() or password.isalpha():
        return "Usa letras e números (ou símbolos) na password."
    return None


def main(argv: list[str]) -> int:
    """Cria ou atualiza a conta admin; devolve o código de saída."""
    reset = "--reset-password" in argv
    args = [a for a in argv if not a.startswith("--")]
    username = (args[0] if args else os.getenv("ADMIN_USERNAME", "")).strip().lower()
    if not USERNAME_RE.match(username):
        print("Indica o username (3–32: letras minúsculas, números, . _ -) ou define ADMIN_USERNAME.")
        return 2

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        row = conn.execute("SELECT role FROM users WHERE username = %s", (username,)).fetchone()
        if row and row[0] != "admin":
            print(f"'{username}' já existe com o perfil '{row[0]}'. Escolhe outro nome para o admin.")
            return 1
        if row and not reset:
            print(f"OK admin '{username}' já existe (a password não mudou; usa --reset-password).")
            return _set_admin_email(conn, username)

        password = os.getenv("ADMIN_PASSWORD") if not args else None
        if not password:
            password = getpass.getpass(f"Password para '{username}': ")
            if getpass.getpass("Repete a password: ") != password:
                print("As passwords não coincidem.")
                return 1
        problem = check_admin_password(username, password)
        if problem:
            print(problem)
            return 1

        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        if row:
            conn.execute("UPDATE users SET password_hash = %s, active = true WHERE username = %s",
                         (hashed, username))
            print(f"OK password do admin '{username}' atualizada.")
        else:
            conn.execute(
                "INSERT INTO users (username, password_hash, role, protected) VALUES (%s, %s, 'admin', true)",
                (username, hashed))
            print(f"OK admin '{username}' criado. Entra em http://localhost:8001/login")
        return _set_admin_email(conn, username)


def _set_admin_email(conn, username: str) -> int:
    """ADMIN_EMAIL (opcional) → email do admin, para poder recuperar a password por email."""
    from multistore_ai_assistant.api.permissions import AccessDenied
    from multistore_ai_assistant.api.users import normalize_email

    raw = os.getenv("ADMIN_EMAIL", "").strip()
    if not raw:
        return 0
    try:
        email = normalize_email(raw)
    except AccessDenied:
        print("ADMIN_EMAIL inválido: o email do admin não mudou.")
        return 1
    try:
        conn.execute("UPDATE users SET email = %s WHERE username = %s", (email, username))
    except psycopg.errors.UniqueViolation:
        print("ADMIN_EMAIL já pertence a outra conta: o email do admin não mudou.")
        return 1
    print(f"OK email do admin '{username}' definido.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
