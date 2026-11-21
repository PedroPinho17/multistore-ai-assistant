"""Gestão de contas (módulo ``users``): ``/users``."""
import logging

from fastapi import APIRouter, Depends

from multistore_ai_assistant.api import users as users_db
from multistore_ai_assistant.api.deps import require_feature, require_module, users_limiter
from multistore_ai_assistant.api.schemas import NewUserIn, UserPatchIn

router = APIRouter(prefix="/users", tags=["users"])
log = logging.getLogger("multistore")
_users_module = require_module("users", users_limiter)
_users_feature = require_feature("users")


def users_user(user: dict = Depends(_users_module), _feature: dict = Depends(_users_feature)) -> dict:
    """A conta tem o módulo ``users`` e o perfil tem a funcionalidade ``users``."""
    return user


@router.get("")
def users(user: dict = Depends(users_user)):
    """Contas que o utilizador pode ver/gerir (do seu nível ou abaixo, no seu âmbito)."""
    return users_db.list_users(user)


@router.get("/options")
def users_options(user: dict = Depends(users_user)):
    """Perfis, marcas, lojas e módulos que o utilizador pode dar a uma conta nova."""
    return users_db.options(user)


@router.post("", status_code=201)
def users_create(body: NewUserIn, user: dict = Depends(users_user)):
    """Cria uma conta do mesmo nível ou abaixo."""
    created = users_db.create_user(user, body.username, body.password, body.role,
                                   body.brand_id, body.store_id, body.modules, body.email)
    log.info("Conta %r (%s) criada por %r", created["username"], created["role"], user["username"])
    return created


@router.patch("/{user_id}")
def users_update(user_id: int, body: UserPatchIn, user: dict = Depends(users_user)):
    """Altera módulos, ativa/desativa ou repõe a password de uma conta gerida."""
    updated = users_db.update_user(user, user_id, body.modules, body.active, body.password, body.email)
    log.info("Conta %r alterada por %r", updated["username"], user["username"])
    return updated


@router.delete("/{user_id}")
def users_delete(user_id: int, user: dict = Depends(users_user)):
    """Apaga uma conta gerida."""
    users_db.delete_user(user, user_id)
    log.info("Conta %s apagada por %r", user_id, user["username"])
    return {"ok": True}
