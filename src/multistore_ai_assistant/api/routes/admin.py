"""Painel de observabilidade (módulo ``observability``, só admin): ``/admin``."""
from fastapi import APIRouter, Depends, Query

from multistore_ai_assistant.api import admin as admin_metrics
from multistore_ai_assistant.api.deps import admin_limiter, require_module

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/metrics")
def metrics(days: int = Query(7, ge=1, le=90),
            user: dict = Depends(require_module("observability", admin_limiter))):
    """Métricas dos últimos ``days`` dias + histórico da avaliação automática."""
    return admin_metrics.metrics(days)
