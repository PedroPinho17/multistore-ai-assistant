"""Perguntas ao assistente (``/ask``, ``/ask/stream``), explicação do SQL
(``/explain``), alertas (``/alerts``), avaliações 👍/👎 e exemplos RAG.

``/ask/stream`` devolve Server-Sent Events: ``status`` (passo atual), ``data``
(SQL, colunas e linhas), ``token`` (pedaços do texto) e, no fim, ``done`` com o
mesmo corpo que o ``/ask`` (ou ``error``). A pergunta corre numa thread e os
eventos passam por uma fila, por isso o RLS, o registo e a conversa são iguais
nos dois caminhos.
"""
import json
import logging
import queue
import threading

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from openai import RateLimitError

from multistore_ai_assistant.api.alerts import alerts_for
from multistore_ai_assistant.api.auth import current_user
from multistore_ai_assistant.api.conversations import (
    add_message,
    create_conversation,
    get_history,
    owns,
    sql_of_request,
)
from multistore_ai_assistant.api.deps import ask_limiter, conversation_user, explain_limiter, require_module
from multistore_ai_assistant.api.errors import ApiError, request_lang, tr
from multistore_ai_assistant.api.permissions import data_role, has_module
from multistore_ai_assistant.api.request_log import rate, save_request
from multistore_ai_assistant.api.review import teachable_sql
from multistore_ai_assistant.api.schemas import AskIn, ExplainIn, FeedbackIn, RatingIn
from multistore_ai_assistant.assistant.answer import explain_sql
from multistore_ai_assistant.assistant.ask import ask
from multistore_ai_assistant.assistant.examples import add_example
from multistore_ai_assistant.assistant.suggest import suggestions
from multistore_ai_assistant.observability import trace

router = APIRouter(tags=["ask"])
log = logging.getLogger("multistore")


def unavailable(lang: str, error: Exception | None = None) -> ApiError:
    """Erro 503 na língua da pergunta (o detalhe técnico fica só no log).

    Quota do LLM esgotada (``openai.RateLimitError``, p.ex. o limite diário da Groq)
    tem mensagem própria: não é uma avaria, passa sozinha.
    """
    err = ApiError("llm_quota" if isinstance(error, RateLimitError) else "unavailable", 503)
    err.lang = lang
    return err


def _check_conversation(body: AskIn, user: dict) -> None:
    ask_limiter.check(user["username"])
    if body.conversation_id is not None and not owns(user["username"], body.conversation_id):
        raise ApiError("conv_not_found", 404)


def handle_ask(body: AskIn, user: dict, on_event=None) -> dict:
    """Responde, grava a troca na conversa e o registo do pedido (comum a /ask e /ask/stream).

    Se ``conversation_id`` for ``None``, cria uma conversa nova com o título
    baseado na primeira pergunta. A resposta traz ``request_id`` para o 👍/👎
    e ``suggestions`` (perguntas de seguimento).
    """
    conv_id = body.conversation_id
    with trace() as t:
        try:
            history = get_history(conv_id) if conv_id is not None else []
            result = ask(body.question, user, body.lang, history, on_event=on_event)
        except Exception as e:
            log.exception("Erro ao responder a %r", body.question)
            t.error = f"{type(e).__name__}: {e}"[:500]
            save_request(t, user, body.question, body.lang, "exception", conv_id)
            raise unavailable(body.lang, e) from None
        if conv_id is None:
            conv_id = create_conversation(user["username"], body.question)
        request_id = save_request(t, user, body.question, body.lang, result.get("kind") or "no_sql", conv_id)
    add_message(conv_id, "user", body.question)
    add_message(
        conv_id, "assistant", result.get("error") or result.get("answer", ""),
        result.get("sql"), result.get("kind"), request_id,
    )
    follow = suggestions(body.question, result.get("kind") or "", result.get("columns"), result.get("rows"),
                         body.lang, data_role(user["role"]))
    return {**result, "conversation_id": conv_id, "request_id": request_id, "suggestions": follow}


@router.post("/ask")
def ask_endpoint(body: AskIn, user: dict = Depends(current_user)):
    """Responde a uma pergunta de uma vez (JSON)."""
    _check_conversation(body, user)
    return handle_ask(body, user)


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


@router.post("/ask/stream")
def ask_stream(body: AskIn, user: dict = Depends(current_user)):
    """Como o ``/ask``, mas em Server-Sent Events à medida que a resposta é gerada."""
    _check_conversation(body, user)        # erros de acesso ainda saem como JSON normal
    events: queue.Queue = queue.Queue()

    def work():
        try:
            events.put({"type": "done", **handle_ask(body, user, events.put)})
        except ApiError as e:
            events.put({"type": "error", "code": e.code, "message": tr(e.code, body.lang, **e.params)})
        except Exception:                  # handle_ask já registou; nunca deixar o cliente pendurado
            log.exception("Erro no streaming")
            events.put({"type": "error", "code": "unavailable", "message": tr("unavailable", body.lang)})
        finally:
            events.put(None)

    threading.Thread(target=work, daemon=True, name="ask-stream").start()

    def stream():
        while (event := events.get()) is not None:
            yield _sse(event)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"X-Accel-Buffering": "no"})


@router.post("/explain")
def explain(body: ExplainIn, user: dict = Depends(require_module("sql", explain_limiter))):
    """Explica em linguagem simples o SQL de uma resposta da própria conta."""
    sql = sql_of_request(user["username"], body.request_id)
    if sql is None:
        raise ApiError("answer_not_found", 404)
    try:
        return {"explanation": explain_sql(sql, body.lang)}
    except Exception as e:
        log.exception("Erro ao explicar SQL")
        raise unavailable(body.lang, e) from None


@router.get("/alerts")
def alerts(request: Request, user: dict = Depends(conversation_user)):
    """Alertas do âmbito do utilizador (quedas de vendas, stock a acabar)."""
    return {"alerts": alerts_for(user, request_lang(request))}


@router.post("/ratings")
def rating(body: RatingIn, user: dict = Depends(conversation_user)):
    """👍 / 👎 numa resposta da própria conta (alimenta o painel de observabilidade)."""
    if not rate(user, body.request_id, body.rating):
        raise ApiError("answer_not_found", 404)
    return {"ok": True}


@router.post("/feedback")
def feedback(body: FeedbackIn, user: dict = Depends(current_user)):
    """Valida SQL e adiciona o par pergunta→SQL ao RAG (módulo ``teach``)."""
    # Os exemplos servem a todas as contas: só quem tem o módulo os pode ensinar
    if not has_module(user, "teach"):
        raise ApiError("cannot_teach", 403)
    add_example(body.question, teachable_sql(body.sql, user), source="feedback", created_by=user["username"])
    return {"ok": True}
