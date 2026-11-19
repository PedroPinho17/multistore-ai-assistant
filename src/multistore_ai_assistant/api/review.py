"""Revisão dos 👎: o feedback de todos melhora o RAG, mas só com a aprovação de quem tem ``teach``.

Fluxo:

1. Um utilizador dá 👎 a uma resposta (``request_log.rating = -1``).
2. A resposta aparece em "Para rever" a quem tem o módulo ``teach`` (admin e
   Imperador; ``permissions.ROLE_MODULES`` não o deixa dar a marcas nem lojas).
3. O revisor corrige o SQL, testa-o (``preview``, com o RLS dele) e:
   - **ensina**: o par pergunta → SQL passa pelo validador e por ``EXPLAIN`` (as
     mesmas regras do ``/feedback``) e entra em ``sql_examples``;
   - **ignora**: a resposta sai da lista sem mexer nos exemplos.
4. Os dois casos ficam registados (``reviewed_at``, ``reviewed_by``, ``review_action``).

O SQL original não está no ``request_log``: vem da mensagem do assistente com o
mesmo ``request_id``. Respostas de previsão (``forecast``/``orders``) não têm SQL
para corrigir: só se podem ignorar.
"""
import psycopg

from multistore_ai_assistant.api.errors import ApiError
from multistore_ai_assistant.assistant.examples import add_example
from multistore_ai_assistant.assistant.sql_validator import InvalidSQL, validate_sql
from multistore_ai_assistant.db.pool import connection
from multistore_ai_assistant.db.query import run_query

MAX_ITEMS = 50
PREVIEW_ROWS = 20
NOT_SQL_KINDS = ("forecast", "orders")

_PENDING = "l.rating = -1 AND l.reviewed_at IS NULL"


def teachable_sql(sql: str, user: dict) -> str:
    """SQL pronto a ensinar: validado e a correr nesta BD (``EXPLAIN`` não executa a query)."""
    try:
        sql = validate_sql(sql)
        run_query(f"EXPLAIN {sql}", user)
    except InvalidSQL as e:
        raise ApiError("invalid_sql", 400, reason=str(e)) from None
    except psycopg.Error:
        raise ApiError("sql_not_running", 400) from None
    return sql


def pending() -> dict:
    """👎 por rever (mais recentes primeiro) e o total."""
    with connection("owner") as conn:
        total = conn.execute(f"SELECT count(*) FROM request_log l WHERE {_PENDING}").fetchone()[0]
        rows = conn.execute(f"""
            SELECT l.id, l.created_at, l.username, l.role, l.question, l.kind, l.error, l.lang,
                   m.sql, m.content,
                   EXISTS (SELECT 1 FROM request_log p
                           WHERE p.conversation_id = l.conversation_id AND p.id < l.id) AS follow_up
            FROM request_log l
            LEFT JOIN messages m ON m.request_id = l.id AND m.role = 'assistant'
            WHERE {_PENDING}
            ORDER BY l.created_at DESC
            LIMIT {MAX_ITEMS}""").fetchall()
    items = [{"id": r[0], "created_at": r[1].isoformat(), "username": r[2], "role": r[3], "question": r[4],
              "kind": r[5], "error": r[6], "lang": r[7], "sql": r[8], "answer": r[9], "follow_up": r[10],
              "can_teach": r[5] not in NOT_SQL_KINDS}
             for r in rows]
    return {"pending": total, "items": items}


def _get_pending(request_id: int) -> dict:
    with connection("owner") as conn:
        row = conn.execute(f"SELECT l.id, l.kind FROM request_log l WHERE l.id = %s AND {_PENDING}",
                           (request_id,)).fetchone()
    if row is None:
        raise ApiError("review_not_found", 404)
    return {"id": row[0], "kind": row[1]}


def _mark(request_id: int, reviewer: dict, action: str, conn=None) -> None:
    """Tira o 👎 da lista. Se entretanto outra pessoa o reviu, ``review_not_found`` (e a transação volta atrás)."""
    if conn is None:
        with connection("owner") as own:
            _mark(request_id, reviewer, action, conn=own)
        return
    cur = conn.execute(f"""UPDATE request_log l SET reviewed_at = now(), reviewed_by = %s, review_action = %s
                           WHERE l.id = %s AND {_PENDING}""",
                       (reviewer["username"], action, request_id))
    if cur.rowcount != 1:
        raise ApiError("review_not_found", 404)


def preview(request_id: int, sql: str, reviewer: dict) -> dict:
    """Corre o SQL corrigido com o RLS de quem revê, para ver o resultado antes de ensinar."""
    _get_pending(request_id)
    return run_preview(sql, reviewer)


def run_preview(sql: str, user: dict) -> dict:
    """Valida e corre um SELECT com o RLS de ``user``; devolve as primeiras ``PREVIEW_ROWS`` linhas."""
    try:
        sql = validate_sql(sql)
        columns, rows = run_query(sql, user)
    except InvalidSQL as e:
        raise ApiError("invalid_sql", 400, reason=str(e)) from None
    except psycopg.Error:
        raise ApiError("sql_not_running", 400) from None
    return {"sql": sql, "columns": columns, "rows": rows[:PREVIEW_ROWS], "row_count": len(rows)}


def teach(request_id: int, question: str, sql: str, reviewer: dict) -> None:
    """Valida, guarda o par nos exemplos RAG e tira o 👎 da lista."""
    item = _get_pending(request_id)
    if item["kind"] in NOT_SQL_KINDS:
        raise ApiError("review_not_sql", 400)
    sql = teachable_sql(sql, reviewer)              # valida e faz EXPLAIN antes de abrir a transação
    # Exemplo e 👎 na mesma transação: ou fica tudo gravado, ou nada (o 👎 nunca sai da lista sem o exemplo)
    with connection("owner") as conn:
        add_example(question.strip(), sql, source="review", created_by=reviewer["username"], conn=conn)
        _mark(request_id, reviewer, "taught", conn=conn)


def dismiss(request_id: int, reviewer: dict) -> None:
    """Tira o 👎 da lista sem ensinar nada."""
    _get_pending(request_id)
    _mark(request_id, reviewer, "dismissed")
