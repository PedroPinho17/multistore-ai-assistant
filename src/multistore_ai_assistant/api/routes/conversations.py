"""Conversas guardadas da própria conta (``/conversations``)."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response

from multistore_ai_assistant.api.auth import current_user
from multistore_ai_assistant.api.conversations import (
    conversation_title,
    delete_conversation,
    get_messages,
    list_conversations,
    rename_conversation,
)
from multistore_ai_assistant.api.deps import conversation_user, pdf_limiter
from multistore_ai_assistant.api.errors import ApiError, request_lang
from multistore_ai_assistant.api.pdf_export import conversation_pdf
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


@router.get("/{conv_id}/pdf")
def conversation_as_pdf(conv_id: int, request: Request, user: dict = Depends(current_user)):
    """PDF da conversa (só da própria conta): perguntas, respostas, SQL e as tabelas guardadas.

    Não corre nada na BD além de ler a conversa: as tabelas são as linhas guardadas
    com cada resposta. Limite próprio (``pdf_limiter``): gerar um PDF custa mais do
    que os outros pedidos às conversas.
    """
    pdf_limiter.check(user["username"])
    title = conversation_title(user["username"], conv_id)
    if title is None:
        raise ApiError("conv_not_found", 404)
    msgs = get_messages(user["username"], conv_id, with_results=True) or []
    pdf = conversation_pdf(title, msgs, request_lang(request))
    # Só ASCII no filename (cabeçalhos HTTP); letras acentuadas viram "_"
    safe = "".join(c if ("A" <= c <= "Z") or ("a" <= c <= "z") or c.isdigit() or c in "-_." else "_"
                   for c in title).strip("._")[:60] or "conversation"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe}.pdf"'},
    )
