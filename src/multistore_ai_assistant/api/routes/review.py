"""Revisão dos 👎 (módulo ``teach``: admin e Imperador): ``/review``."""
from fastapi import APIRouter, Depends

from multistore_ai_assistant.api import review as review_db
from multistore_ai_assistant.api.deps import require_feature, require_module, review_limiter
from multistore_ai_assistant.api.schemas import ReviewSqlIn, ReviewTeachIn

router = APIRouter(prefix="/review", tags=["review"])
reviewer = require_module("teach", review_limiter)
review_feature = require_feature("review")


@router.get("")
def pending(user: dict = Depends(reviewer), _feature: dict = Depends(review_feature)):
    """Respostas com 👎 por rever: pergunta, resposta, SQL usado, quem perguntou."""
    return review_db.pending()


@router.post("/{request_id}/preview")
def preview(request_id: int, body: ReviewSqlIn, user: dict = Depends(reviewer), _feature: dict = Depends(review_feature)):
    """Corre o SQL corrigido (validado, com o RLS de quem revê) e devolve as primeiras linhas."""
    return review_db.preview(request_id, body.sql, user)


@router.post("/{request_id}/teach")
def teach(request_id: int, body: ReviewTeachIn, user: dict = Depends(reviewer), _feature: dict = Depends(review_feature)):
    """Guarda pergunta → SQL corrigido nos exemplos RAG e tira o 👎 da lista."""
    review_db.teach(request_id, body.question, body.sql, user)
    return {"ok": True}


@router.post("/{request_id}/dismiss")
def dismiss(request_id: int, user: dict = Depends(reviewer), _feature: dict = Depends(review_feature)):
    """Tira o 👎 da lista sem ensinar nada."""
    review_db.dismiss(request_id, user)
    return {"ok": True}
