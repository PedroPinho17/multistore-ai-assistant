"""Página de perfil: estatísticas, password e email (``/profile``; a foto está em ``routes/avatars``)."""
import logging

from fastapi import APIRouter, Depends

from multistore_ai_assistant.api.auth import create_token, current_user
from multistore_ai_assistant.api.deps import conversation_user, password_limiter
from multistore_ai_assistant.api.errors import ApiError
from multistore_ai_assistant.api.permissions import require_not_demo
from multistore_ai_assistant.api.profile import PasswordError, change_password, get_profile
from multistore_ai_assistant.api.schemas import EmailIn, PasswordIn
from multistore_ai_assistant.api.users import normalize_email, set_email
from multistore_ai_assistant.db.pool import connection

router = APIRouter(prefix="/profile", tags=["profile"])
log = logging.getLogger("multistore")


@router.get("")
def profile(user: dict = Depends(conversation_user)):
    """Perfil com o âmbito (marca / loja) e estatísticas de utilização."""
    return get_profile(user)


@router.post("/password")
def profile_password(body: PasswordIn, user: dict = Depends(current_user)):
    """Muda a password do próprio utilizador.

    Devolve 400 (e não 401) quando a password atual está errada,
    para a UI não interpretar o erro como sessão expirada.

    A mudança revoga todas as sessões da conta (``token_version`` + 1), incluindo
    o token deste pedido; a resposta traz um token novo para quem mudou continuar.
    """
    require_not_demo(user)                # a password é pública: mudá-la trancava a demo a toda a gente
    password_limiter.check(user["username"])
    try:
        version = change_password(user["username"], body.current_password, body.new_password)
    except PasswordError as e:
        raise ApiError(e.code, 400, str(e), **e.params) from None
    if version is None:                   # a conta foi apagada a meio do pedido
        raise ApiError("session_invalid", 401)
    log.info("Password alterada por %r", user["username"])
    return {"ok": True, "token": create_token({**user, "token_version": version})}


@router.put("/email")
def profile_email(body: EmailIn, user: dict = Depends(conversation_user)):
    """Email da própria conta (para recuperar a password); vazio ou ``null`` tira-o."""
    require_not_demo(user)                # contas de demo: a password é pública, não se recupera
    email = normalize_email(body.email)
    with connection("owner") as conn:
        set_email(conn, user["id"], email)
    log.info("Email da conta %r %s", user["username"], "alterado" if email else "removido")
    return {"email": email}
