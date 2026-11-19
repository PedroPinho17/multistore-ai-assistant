"""Exemplos do RAG (módulo ``teach``: admin e Imperador): ``/examples``."""
from fastapi import APIRouter, Depends

from multistore_ai_assistant.api import rag_examples
from multistore_ai_assistant.api import review as review_db
from multistore_ai_assistant.api.deps import require_module, review_limiter
from multistore_ai_assistant.api.schemas import ExampleIn, ReviewSqlIn

router = APIRouter(prefix="/examples", tags=["examples"])
teacher = require_module("teach", review_limiter)


@router.get("")
def list_examples(user: dict = Depends(teacher)):
    """Todos os exemplos com origem, autor e quantas vezes entraram num prompt."""
    return {"examples": rag_examples.list_examples()}


@router.post("/preview")
def preview(body: ReviewSqlIn, user: dict = Depends(teacher)):
    """Valida e corre o SQL com o RLS de quem edita (primeiras 20 linhas)."""
    return review_db.run_preview(body.sql, user)


@router.post("", status_code=201)
def create(body: ExampleIn, user: dict = Depends(teacher)):
    """Exemplo novo; 409 se a pergunta já existir."""
    return {"id": rag_examples.create(body.question, body.sql, user)}


@router.put("/{example_id}")
def update(example_id: int, body: ExampleIn, user: dict = Depends(teacher)):
    """Corrige pergunta e SQL (validados como no /feedback)."""
    rag_examples.update(example_id, body.question, body.sql, user)
    return {"ok": True}


@router.delete("/{example_id}")
def delete(example_id: int, user: dict = Depends(teacher)):
    rag_examples.delete(example_id)
    return {"ok": True}
