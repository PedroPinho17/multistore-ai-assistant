"""Define palavras-passe (com hash) para os utilizadores de demonstração
e a password do role só de leitura 'assistente' (lida de READONLY_DATABASE_URL).

Por defeito só preenche utilizadores SEM password: assim, quem mudou a password
na página de perfil não a perde quando o Docker reinicia.
Para repor as passwords de demonstração:  python -m ...data.set_passwords --reset
"""
import os
import sys
from urllib.parse import unquote, urlparse

import bcrypt
import psycopg
from dotenv import load_dotenv
from psycopg import sql

load_dotenv()

DEMO_PASSWORDS = {
    "pedro": "imperador123",
    "gestor.burgerlab": "marca123",
    "gerente.maia": "loja123",
}


def main(reset: bool = False) -> None:
    """Grava hashes bcrypt dos users demo e sincroniza a password do role ``assistente``."""
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        for username, password in DEMO_PASSWORDS.items():
            hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
            cur = conn.execute(
                "UPDATE users SET password_hash = %s WHERE username = %s"
                " AND (password_hash IS NULL OR %s)",
                (hashed, username, reset),
            )
            print("OK" if cur.rowcount else "--", username,
                  "" if cur.rowcount else "(já tem password; usa --reset para repor)")

        readonly = urlparse(os.environ["READONLY_DATABASE_URL"])
        if readonly.username and readonly.password:
            conn.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                sql.Identifier(unquote(readonly.username)),
                sql.Literal(unquote(readonly.password)),
            ))
            print("OK role", readonly.username, "(password de READONLY_DATABASE_URL)")


if __name__ == "__main__":
    main(reset="--reset" in sys.argv[1:])
