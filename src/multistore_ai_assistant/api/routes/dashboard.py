"""Painel de KPIs de vendas (``GET /dashboard``), filtrado pelo RLS do perfil."""
from fastapi import APIRouter, Depends

from multistore_ai_assistant.api.dashboard import dashboard_for
from multistore_ai_assistant.api.deps import conversation_user

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
def dashboard(user: dict = Depends(conversation_user)):
    """Faturação do mês, top lojas, margem por marca e previsão a 7 dias.

    Os números respeitam o RLS (grupo / marca / loja) do utilizador autenticado.
    """
    return dashboard_for(user)
