"""Página de perfil: estatísticas, password e foto (``/profile``)."""
import logging

from fastapi import APIRouter, Depends

from multistore_ai_assistant.api.auth import current_user
from multistore_ai_assistant.api.deps import conversation_user, password_limiter
from multistore_ai_assistant.api.errors import ApiError
from multistore_ai_assistant.api.permissions import require_not_demo
from multistore_ai_assistant.api.profile import AvatarError, PasswordError, change_password, get_profile, set_avatar
from multistore_ai_assistant.api.schemas import AvatarIn, EmailIn, PasswordIn
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
    require_not_demo(user)                # a password é pública: mudá-la trancava a demo a toda a gente
    """Muda a password do próprio utilizador.

    Devolve 400 (e não 401) quando a password atual está errada,
    para a UI não interpretar o erro como sessão expirada.
    """
    password_limiter.check(user["username"])
    try:
        change_password(user["username"], body.current_password, body.new_password)
    except PasswordError as e:
        raise ApiError(e.code, 400, str(e), **e.params) from None
    log.info("Password alterada por %r", user["username"])
    return {"ok": True}


@router.put("/email")
def profile_email(body: EmailIn, user: dict = Depends(conversation_user)):
    """Email da própria conta (para recuperar a password); vazio ou ``null`` tira-o."""
    require_not_demo(user)                # contas de demo: a password é pública, não se recupera
    email = normalize_email(body.email)
    with connection("owner") as conn:
        set_email(conn, user["id"], email)
    log.info("Email da conta %r %s", user["username"], "alterado" if email else "removido")
    return {"email": email}


@router.post("/avatar")
def profile_avatar(body: AvatarIn, user: dict = Depends(conversation_user)):
    require_not_demo(user)                # a foto da conta de demo aparecia a todos os visitantes
    """Guarda a foto de perfil (validada: tipo, tamanho e bytes da imagem)."""
    try:
        set_avatar(user["username"], body.image)
    except AvatarError as e:
        raise ApiError(e.code, 400, str(e)) from None
    return {"ok": True}


@router.delete("/avatar")
def profile_avatar_delete(user: dict = Depends(conversation_user)):
    require_not_demo(user)
    """Remove a foto de perfil (volta o logótipo da marca ou do grupo)."""
    set_avatar(user["username"], None)
    return {"ok": True}
