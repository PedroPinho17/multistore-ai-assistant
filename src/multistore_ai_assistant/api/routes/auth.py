"""Login e perfil atual (``/login``, ``/me``)."""
import logging

from fastapi import APIRouter, Depends, Request

from multistore_ai_assistant.api import settings as settings_db
from multistore_ai_assistant.api.auth import authenticate, create_token, current_user, public_user
from multistore_ai_assistant.api.deps import client_ip, login_limiter
from multistore_ai_assistant.api.errors import ApiError
from multistore_ai_assistant.api.profile import me_details
from multistore_ai_assistant.api.schemas import LoginIn

router = APIRouter(tags=["auth"])
log = logging.getLogger("multistore")


@router.post("/login")
def login(body: LoginIn, request: Request):
    """Autentica com bcrypt e devolve JWT + perfil (role / marca / loja / módulos)."""
    login_limiter.check(client_ip(request))
    user = authenticate(body.username, body.password)
    if not user:
        log.warning("Login falhado para %r a partir de %s", body.username, client_ip(request))
        raise ApiError("bad_login", 401)
    return {"token": create_token(user), "user": public_user(user)}


@router.get("/me")
def me(user: dict = Depends(current_user)):
    """Perfil atual (sem password), com a foto, a marca e as definições da conta."""
    return {**public_user(user), **me_details(user), "settings": settings_db.get_user_settings(user)}
