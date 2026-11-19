"""Registo de cada pergunta (tabela ``request_log``) e avaliação 👍/👎.

Gravar o registo nunca pode fazer falhar a resposta ao utilizador: se a BD
recusar o INSERT, fica um aviso no log do servidor e a resposta segue.
"""
import logging

from multistore_ai_assistant.db.pool import connection
from multistore_ai_assistant.observability import Trace

log = logging.getLogger("multistore")
MAX_QUESTION = 500


def save_request(t: Trace, user: dict, question: str, lang: str, kind: str,
                 conversation_id: int | None = None) -> int | None:
    """Grava o registo de uma pergunta e devolve o id (``None`` se falhar)."""
    try:
        with connection("owner") as conn:
            return conn.execute(
                """INSERT INTO request_log
                     (user_id, username, role, conversation_id, question, lang, intent, confidence,
                      kind, sql_attempts, sql_failed, error, duration_ms, llm_calls,
                      prompt_tokens, completion_tokens, cache_hit)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   RETURNING id""",
                (user.get("id"), user["username"], user["role"], conversation_id,
                 question[:MAX_QUESTION], lang, t.intent, t.confidence, kind, t.sql_attempts,
                 t.sql_failed, t.error, t.duration_ms(), t.llm_calls, t.prompt_tokens,
                 t.completion_tokens, t.cache_hit),
            ).fetchone()[0]
    except Exception:
        log.warning("Não foi possível gravar o registo do pedido", exc_info=True)
        return None


def rate(user: dict, request_id: int, rating: int) -> bool:
    """Guarda 👍 (1), 👎 (-1) ou tira a avaliação (0) de uma resposta da própria conta."""
    with connection("owner") as conn:
        cur = conn.execute(
            """UPDATE request_log
               SET rating = %s, rated_at = CASE WHEN %s THEN now() END
               WHERE id = %s AND user_id = %s""",
            (rating or None, bool(rating), request_id, user["id"]),
        )
        return cur.rowcount == 1
