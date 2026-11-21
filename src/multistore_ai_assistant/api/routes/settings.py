"""Definições da conta e da aplicação (``/config``, ``/settings``)."""
import logging

from fastapi import APIRouter, Depends

from multistore_ai_assistant.api import settings as settings_db
from multistore_ai_assistant.api.deps import admin_user, conversation_user, require_feature
from multistore_ai_assistant.api.schemas import AppSettingsIn, UserSettingsIn

router = APIRouter(tags=["settings"])
log = logging.getLogger("multistore")


@router.get("/config")
def config():
    """Público: cor e idioma por defeito e se as contas de demonstração aparecem."""
    return settings_db.public_config()


@router.put("/settings/me")
def settings_me(body: UserSettingsIn, user: dict = Depends(conversation_user)):
    """Idioma, tema e cor da própria conta (guardados na BD)."""
    return settings_db.update_user_settings(user, body.model_dump(exclude_unset=True))


@router.get("/settings/app")
def settings_app(user: dict = Depends(admin_user), _feature: dict = Depends(require_feature("admin"))):
    """Definições da aplicação, quem as mudou por último e os valores possíveis."""
    return settings_db.app_settings_details()


@router.put("/settings/app")
def settings_app_update(body: AppSettingsIn, user: dict = Depends(admin_user),
                        _feature: dict = Depends(require_feature("admin"))):
    """Muda as definições da aplicação (só os campos enviados)."""
    changes = {k: v for k, v in body.model_dump(exclude_unset=True).items() if v is not None}
    result = settings_db.update_app_settings(user, changes)
    log.info("Definições da aplicação alteradas por %r: %s", user["username"], changes)
    return result
