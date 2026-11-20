"""Autenticação: bcrypt na BD + JWT assinado (HS256).

O login demora o mesmo tempo quer o utilizador exista ou não (hash dummy),
para não revelar se o username é válido.

O token só prova *quem* é o utilizador. O perfil, o âmbito e os módulos são
lidos da BD em cada pedido (``load_user``): desativar uma conta ou tirar-lhe
um módulo tem efeito imediato, sem esperar que o token expire.

Revogação: cada JWT leva ``tv`` (a ``token_version`` da conta quando foi emitido).
Mudar ou repor a password soma 1 a ``token_version`` (``BUMP_TOKEN_VERSION``) e os
tokens com outro ``tv`` deixam de valer. Sem ``tv``, ou com um valor inválido, o
token é recusado (falha fechada).
"""
import os
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from dotenv import load_dotenv
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from multistore_ai_assistant.api import settings as app_settings
from multistore_ai_assistant.api.errors import ApiError
from multistore_ai_assistant.api.permissions import ROLES, effective_modules, is_demo
from multistore_ai_assistant.db.pool import connection

load_dotenv()

SECRET = os.environ["JWT_SECRET"]
if len(SECRET) < 32 or SECRET.startswith("change-me"):
    raise RuntimeError(
        "JWT_SECRET tem de ter pelo menos 32 caracteres aleatórios "
        '(gera um com: python -c "import secrets; print(secrets.token_urlsafe(48))").'
    )

ALGORITHM = "HS256"
TOKEN_HOURS = 8          # predefinição; o admin muda em Definições → "session_hours"
bearer = HTTPBearer()

# Hash falso: o login demora o mesmo tempo quer o utilizador exista ou não
_DUMMY_HASH = bcrypt.hashpw(b"dummy-password", bcrypt.gensalt())

USER_COLUMNS = "id, username, role, brand_id, store_id, modules, protected, token_version"
# SQL que revoga todas as sessões da conta; junta-se ao UPDATE que grava o novo hash
BUMP_TOKEN_VERSION = "token_version = token_version + 1"
_USER_FIELDS = 8         # colunas em USER_COLUMNS (password_hash / active vêm a seguir no login)


def _check_password(password: str, hashed: bytes) -> bool:
    """Compara password com hash bcrypt; devolve False se o hash for inválido."""
    try:
        return bcrypt.checkpw(password.encode(), hashed)
    except ValueError:  # p.ex. password com mais de 72 bytes
        return False


def _to_user(row) -> dict:
    """Linha ``USER_COLUMNS`` → perfil usado pela API (com os módulos efetivos)."""
    uid, username, role, brand_id, store_id, modules, protected, token_version = row
    return {"id": uid, "username": username, "role": role, "brand_id": brand_id,
            "store_id": store_id, "modules": effective_modules(role, modules),
            "protected": bool(protected), "token_version": token_version}


def authenticate(username: str, password: str) -> dict | None:
    """Valida credenciais na tabela ``users`` (contas desativadas não entram).

    Returns:
        Perfil (id, username, role, brand_id, store_id, modules) ou ``None``.
    """
    with connection() as conn:
        row = conn.execute(
            f"SELECT {USER_COLUMNS}, password_hash, active FROM users WHERE username = %s",
            (username,),
        ).fetchone()
        hashed, active = (row[_USER_FIELDS], row[_USER_FIELDS + 1]) if row else (None, None)
        if not row or not hashed or not active:
            _check_password(password, _DUMMY_HASH)
            return None
        if not _check_password(password, hashed.encode()):
            return None
        conn.execute("UPDATE users SET last_login = now() WHERE id = %s", (row[0],))
    return _to_user(row[:_USER_FIELDS])


def load_user(username: str) -> dict | None:
    """Perfil atual de uma conta ativa, ou ``None`` (apagada ou desativada)."""
    with connection() as conn:
        row = conn.execute(
            f"SELECT {USER_COLUMNS} FROM users WHERE username = %s AND active", (username,),
        ).fetchone()
    return _to_user(row) if row else None


def public_user(user: dict) -> dict:
    """O que a UI recebe sobre a conta (sem o id interno)."""
    return {**{k: user[k] for k in ("username", "role", "brand_id", "store_id", "modules")},
            "demo": is_demo(user)}


def session_hours() -> int:
    """Duração da sessão definida pelo admin (``TOKEN_HOURS`` se não houver)."""
    return int(app_settings.get_app_settings().get("session_hours") or TOKEN_HOURS)


def create_token(user: dict, hours: int | None = None) -> str:
    """Emite um JWT com a identidade, a versão da conta (``tv``) e a validade da sessão (horas)."""
    now = datetime.now(UTC)
    payload = {
        "sub": user["username"],
        "role": user["role"],
        "tv": int(user["token_version"]),       # sem versão não há token (KeyError): nunca emite um irrevogável
        "iat": now,
        "exp": now + timedelta(hours=hours or session_hours()),
    }
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)


def _is_version(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)       # True == 1 em Python


def token_version_matches(claim, current) -> bool:
    """O ``tv`` do token é a versão atual da conta? Qualquer coisa estranha conta como não."""
    return _is_version(claim) and _is_version(current) and claim == current


def current_user(creds: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    """Dependência FastAPI: valida o Bearer token e devolve o perfil atual (da BD).

    Raises:
        ApiError 401 (``session_invalid``): token em falta, expirado, de uma versão
        anterior da conta (a password mudou), ou conta apagada/desativada.
    """
    try:
        payload = jwt.decode(
            creds.credentials, SECRET, algorithms=[ALGORITHM],
            options={"require": ["exp", "iat", "sub", "tv"]},
        )
    except jwt.PyJWTError:
        raise ApiError("session_invalid", 401) from None
    user = load_user(payload["sub"])
    if not user or user["role"] not in ROLES:
        raise ApiError("session_invalid", 401)
    if not token_version_matches(payload["tv"], user.get("token_version")):
        raise ApiError("session_invalid", 401)
    return user
