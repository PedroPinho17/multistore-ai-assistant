"""Painel de observabilidade (módulo ``observability``, só admin): ``/admin``."""
from fastapi import APIRouter, Depends, Query

from multistore_ai_assistant.api import admin as admin_metrics
from multistore_ai_assistant.api import features
from multistore_ai_assistant.api.deps import admin_limiter, admin_user, require_feature, require_module
from multistore_ai_assistant.api.schemas import RoleFeaturesIn

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/metrics")
def metrics(days: int = Query(7, ge=1, le=90),
            user: dict = Depends(require_module("observability", admin_limiter)),
            _feature: dict = Depends(require_feature("admin"))):
    """Métricas dos últimos ``days`` dias + histórico da avaliação automática."""
    return admin_metrics.metrics(days)


@router.get("/features")
def role_features(user: dict = Depends(admin_user),
                  _feature: dict = Depends(require_feature("admin"))):
    """Funcionalidades de cada perfil (só o perfil admin, com a funcionalidade admin)."""
    return features.matrix()


@router.put("/features")
def update_role_features(body: RoleFeaturesIn,
                         user: dict = Depends(admin_user),
                         _feature: dict = Depends(require_feature("admin"))):
    """Substitui as funcionalidades de um perfil."""
    chosen = features.set_role_features(body.role, list(body.features))
    return {"role": body.role, "features": chosen}
