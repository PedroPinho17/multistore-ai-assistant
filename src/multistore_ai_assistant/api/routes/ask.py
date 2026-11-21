"""Perguntas ao assistente (``/ask``, ``/ask/stream``), explicação do SQL
(``/explain``), alertas (``/alerts``), avaliações 👍/👎 e exemplos RAG.

``/ask/stream`` devolve Server-Sent Events: ``status`` (passo atual), ``data``
(SQL, colunas e linhas), ``token`` (pedaços do texto) e, no fim, ``done`` com o
mesmo corpo que o ``/ask`` (ou ``error``). A pergunta corre numa thread e os
eventos passam por uma fila, por isso o RLS, o registo e a conversa são iguais
nos dois caminhos.
"""
import asyncio
import json
import logging
import queue
import threading
import time

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from openai import RateLimitError

from multistore_ai_assistant.api.alerts import alerts_for
from multistore_ai_assistant.api.auth import current_user
from multistore_ai_assistant.api.conversations import (
    add_exchange,
    create_conversation,
    delete_conversation,
    get_history,
    owns,
    result_payload,
    sql_of_request,
)
from multistore_ai_assistant.api.deps import (
    ask_limiter,
    conv_limiter,
    explain_limiter,
    require_any_feature,
    require_feature,
    require_module,
)
from multistore_ai_assistant.api.errors import ApiError, request_lang, tr
from multistore_ai_assistant.api.features import CHAT_FEATURES, has_any_feature, has_feature
from multistore_ai_assistant.api.json_safe import jsonable
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


class StreamCancelled(Exception):
    """O cliente do ``/ask/stream`` desligou-se: o worker para no próximo evento."""


def _check_conversation(body: AskIn, user: dict) -> None:
    if not has_any_feature(user, CHAT_FEATURES):
        raise ApiError("no_feature", 403, feature="chat")
    ask_limiter.check(user["username"])
    if body.conversation_id is not None and not owns(user["username"], body.conversation_id):
        raise ApiError("conv_not_found", 404)


def handle_ask(body: AskIn, user: dict, on_event=None, cancelled: threading.Event | None = None) -> dict:
    """Responde, grava a troca na conversa e o registo do pedido (comum a /ask e /ask/stream).

    Se ``conversation_id`` for ``None``, cria uma conversa nova com o título
    baseado na primeira pergunta. A resposta traz ``request_id`` para o 👍/👎
    e ``suggestions`` (perguntas de seguimento).

    ``cancelled`` (só no streaming): se o cliente já se desligou quando a resposta fica
    pronta, nada vai para a conversa (levanta ``StreamCancelled``). A pergunta e a resposta
    são gravadas juntas, numa transação: nunca fica uma pergunta sem resposta.
    """
    conv_id = body.conversation_id
    with trace() as t:
        try:
            history = get_history(conv_id) if conv_id is not None else []
            result = ask(body.question, user, body.lang, history, on_event=on_event)
        except StreamCancelled:
            # O cliente desligou-se: não é uma avaria. Fica no registo (os tokens gastos contam)
            # mas não na conversa, que o utilizador não chegou a ver.
            save_request(t, user, body.question, body.lang, "cancelled", conv_id)
            raise
        except Exception as e:
            log.exception("Erro ao responder a %r", body.question)
            t.error = f"{type(e).__name__}: {e}"[:500]
            save_request(t, user, body.question, body.lang, "exception", conv_id)
            raise unavailable(body.lang, e) from None
        if cancelled is not None and cancelled.is_set():
            # Desligou-se depois do último evento (p.ex. uma recusa, que não emite tokens):
            # a resposta existe, mas ninguém a viu. O mesmo tratamento que a meio do streaming.
            save_request(t, user, body.question, body.lang, "cancelled", conv_id)
            raise StreamCancelled
        result = jsonable(result)          # NaN/Infinity → None: JSON válido para a resposta, o SSE e a BD
        stored = result_payload(result.get("columns"), result.get("rows"))   # antes de gravar seja o que for
        created = conv_id is None
        if created:
            conv_id = create_conversation(user["username"], body.question)
        request_id = save_request(t, user, body.question, body.lang, result.get("kind") or "no_sql", conv_id)
    try:
        add_exchange(conv_id, body.question, result.get("error") or result.get("answer", ""),
                     result.get("sql"), result.get("kind"), request_id, stored)
    except Exception as e:
        log.exception("Não foi possível gravar a troca na conversa %s", conv_id)
        if created:                        # não deixar uma conversa vazia na barra lateral
            delete_conversation(user["username"], conv_id)
        raise unavailable(body.lang, e) from None
    follow = suggestions(body.question, result.get("kind") or "", result.get("columns"), result.get("rows"),
                         body.lang, data_role(user["role"]))
    return {**result, "conversation_id": conv_id, "request_id": request_id, "suggestions": follow}


@router.post("/ask")
def ask_endpoint(body: AskIn, user: dict = Depends(current_user)):
    """Responde a uma pergunta de uma vez (JSON)."""
    _check_conversation(body, user)
    return handle_ask(body, user)


def _sse(event: dict) -> str:
    """Um evento SSE. ``allow_nan=False``: um NaN que escape ao ``jsonable`` falha aqui, não no browser."""
    return f"data: {json.dumps(jsonable(event), ensure_ascii=False, allow_nan=False, default=str)}\n\n"


POLL_SECONDS = 0.05        # à espera de eventos: de quanto em quanto tempo vê se o cliente ainda lá está
BUSY_CHECK_SECONDS = 0.5   # a enviar eventos sem parar: verifica pelo menos com esta frequência


@router.post("/ask/stream")
def ask_stream(body: AskIn, request: Request, user: dict = Depends(current_user)):
    """Como o ``/ask``, mas em Server-Sent Events à medida que a resposta é gerada.

    Se o cliente se desligar (fechou o separador, carregou em parar), o worker para no
    próximo evento: o texto do LLM deixa de ser pedido e nada é gravado na conversa.
    """
    _check_conversation(body, user)        # erros de acesso ainda saem como JSON normal
    events: queue.Queue = queue.Queue()
    cancelled = threading.Event()

    def emit(event: dict) -> None:
        if cancelled.is_set():
            raise StreamCancelled
        events.put(event)

    def work():
        try:
            events.put({"type": "done", **handle_ask(body, user, emit, cancelled)})
        except StreamCancelled:
            log.info("Streaming cancelado: %r desligou-se a meio da resposta", user["username"])
        except ApiError as e:
            events.put({"type": "error", "code": e.code, "message": tr(e.code, body.lang, **e.params)})
        except Exception:                  # handle_ask já registou; nunca deixar o cliente pendurado
            log.exception("Erro no streaming")
            events.put({"type": "error", "code": "unavailable", "message": tr("unavailable", body.lang)})
        finally:
            events.put(None)

    threading.Thread(target=work, daemon=True, name="ask-stream").start()

    async def stream():
        last_check = time.monotonic()
        try:
            while True:
                try:
                    event = events.get_nowait()
                except queue.Empty:
                    if await request.is_disconnected():
                        return
                    last_check = time.monotonic()
                    await asyncio.sleep(POLL_SECONDS)
                    continue
                if event is None:
                    return
                yield _sse(event)
                if time.monotonic() - last_check > BUSY_CHECK_SECONDS:   # muitos tokens seguidos
                    last_check = time.monotonic()
                    if await request.is_disconnected():
                        return
        finally:                           # fim normal, desligou-se, ou o Starlette cancelou o stream
            cancelled.set()

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"X-Accel-Buffering": "no"})


@router.post("/explain")
def explain(body: ExplainIn, user: dict = Depends(require_module("sql", explain_limiter)),
           _feature: dict = Depends(require_feature("chat"))):
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
def alerts(request: Request,
           user: dict = Depends(require_any_feature("chat", "orders", limiter=conv_limiter))):
    """Alertas do âmbito do utilizador (quedas de vendas, stock a acabar)."""
    return {"alerts": alerts_for(user, request_lang(request))}


@router.post("/ratings")
def rating(body: RatingIn, user: dict = Depends(require_any_feature(*CHAT_FEATURES, limiter=conv_limiter))):
    """👍 / 👎 numa resposta da própria conta (alimenta o painel de observabilidade)."""
    if not rate(user, body.request_id, body.rating):
        raise ApiError("answer_not_found", 404)
    return {"ok": True}


@router.post("/feedback")
def feedback(body: FeedbackIn, user: dict = Depends(current_user)):
    """Valida SQL e adiciona o par pergunta→SQL ao RAG (módulo ``teach``)."""
    # Os exemplos servem a todas as contas: só quem tem o módulo os pode ensinar
    if not has_feature(user, "review"):
        raise ApiError("no_feature", 403, feature="review")
    if not has_module(user, "teach"):
        raise ApiError("cannot_teach", 403)
    add_example(body.question, teachable_sql(body.sql, user), source="feedback", created_by=user["username"])
    return {"ok": True}
