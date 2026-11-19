"""Conversas guardadas da própria conta (``/conversations``)."""
from fastapi import APIRouter, Depends

from multistore_ai_assistant.api.conversations import (
    delete_conversation,
    get_messages,
    list_conversations,
    rename_conversation,
)
from multistore_ai_assistant.api.deps import conversation_user
from multistore_ai_assistant.api.errors import ApiError
from multistore_ai_assistant.api.profile import delete_all_conversations
from multistore_ai_assistant.api.schemas import RenameIn

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("")
def conversations(user: dict = Depends(conversation_user)):
    """Lista as conversas do utilizador (mais recentes primeiro)."""
    return list_conversations(user["username"])


@router.delete("")
def remove_all_conversations(user: dict = Depends(conversation_user)):
    """Apaga todo o histórico de conversas do utilizador."""
    return {"deleted": delete_all_conversations(user["username"])}


@router.get("/{conv_id}")
def conversation(conv_id: int, user: dict = Depends(conversation_user)):
    """Mensagens de uma conversa; 404 se não for do utilizador."""
    msgs = get_messages(user["username"], conv_id)
    if msgs is None:
        raise ApiError("conv_not_found", 404)
    return msgs


@router.patch("/{conv_id}")
def rename(conv_id: int, body: RenameIn, user: dict = Depends(conversation_user)):
    """Renomeia o título de uma conversa própria."""
    if not body.title.strip() or not rename_conversation(user["username"], conv_id, body.title):
        raise ApiError("conv_not_found", 404)
    return {"ok": True}


@router.delete("/{conv_id}")
def remove_conversation(conv_id: int, user: dict = Depends(conversation_user)):
    """Apaga uma conversa própria (e as suas mensagens, via FK)."""
    if not delete_conversation(user["username"], conv_id):
        raise ApiError("conv_not_found", 404)
    return {"ok": True}
