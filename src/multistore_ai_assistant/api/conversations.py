"""Conversas guardadas por utilizador (lidas e gravadas pela API, nunca pelo LLM).

Todas as queries filtram por ``user_id`` do username autenticado, para um
utilizador não aceder às conversas de outro.
"""
import json
from datetime import date, datetime
from decimal import Decimal

from multistore_ai_assistant.api.json_safe import jsonable
from multistore_ai_assistant.db.pool import connection

# Subquery reutilizada: resolve o id do utilizador a partir do username
USER_ID = "(SELECT id FROM users WHERE username = %s)"


def _conn():
    """Ligação de escrita à BD (dono da app, não o role read-only), vinda do pool."""
    return connection("owner")


def list_conversations(username: str) -> list[dict]:
    """Lista até 50 conversas do utilizador, da mais recente para a mais antiga."""
    with _conn() as conn:
        rows = conn.execute(
            f"SELECT id, title, updated_at FROM conversations WHERE user_id = {USER_ID} "
            "ORDER BY updated_at DESC LIMIT 50", (username,),
        ).fetchall()
    return [{"id": r[0], "title": r[1], "updated_at": r[2].isoformat()} for r in rows]


MAX_STORED_ROWS = 200      # linhas de dados guardadas por resposta (para o PDF); também na CHECK da V014


def _json_value(value):
    """Valores das linhas em JSON: Decimal (já finito) → número, datas → ISO, resto → texto."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def result_payload(columns: list | None, rows: list | None) -> str | None:
    """Os dados de uma resposta, prontos para ``messages.result`` (JSON), ou ``None`` se não há tabela.

    Guarda no máximo ``MAX_STORED_ROWS`` linhas, com ``truncated`` a dizer se havia mais.
    NaN/Infinity (o ``jsonb`` recusa-os) passam a ``null``; ``allow_nan=False`` faz falhar
    aqui, antes de gravar, se algum escapar.
    """
    if not columns:
        return None
    rows = list(rows or [])
    payload = {"columns": [str(c) for c in columns],
               "rows": jsonable([list(r) for r in rows[:MAX_STORED_ROWS]]),
               "truncated": len(rows) > MAX_STORED_ROWS}
    return json.dumps(payload, ensure_ascii=False, allow_nan=False, default=_json_value)


def get_messages(username: str, conv_id: int, with_results: bool = False) -> list[dict] | None:
    """Mensagens de uma conversa, ou ``None`` se não pertencer ao utilizador.

    ``with_results``: inclui ``result`` (as linhas guardadas de cada resposta, para o PDF).
    A UI não as pede: são até 200 linhas por mensagem.
    """
    with _conn() as conn:
        owner = conn.execute(
            f"SELECT 1 FROM conversations WHERE id = %s AND user_id = {USER_ID}",
            (conv_id, username),
        ).fetchone()
        if not owner:
            return None
        rows = conn.execute(
            "SELECT m.role, m.content, m.sql, m.kind, m.created_at, m.request_id, l.rating"
            + (", m.result" if with_results else "") +
            " FROM messages m LEFT JOIN request_log l ON l.id = m.request_id"
            " WHERE m.conversation_id = %s ORDER BY m.id", (conv_id,),
        ).fetchall()
    out = []
    for r in rows:
        msg = {"role": r[0], "content": r[1], "sql": r[2], "kind": r[3],
               "created_at": r[4].isoformat(), "request_id": r[5], "rating": r[6]}
        if with_results:
            msg["result"] = r[7]                 # o psycopg já devolve o jsonb descodificado
        out.append(msg)
    return out


def create_conversation(username: str, first_question: str) -> int:
    """Cria conversa com título derivado da primeira pergunta; devolve o id."""
    title = first_question.strip()
    title = title[:60] + "…" if len(title) > 60 else title
    with _conn() as conn:
        return conn.execute(
            f"INSERT INTO conversations (user_id, title) VALUES ({USER_ID}, %s) RETURNING id",
            (username, title),
        ).fetchone()[0]


def owns(username: str, conv_id: int) -> bool:
    """True se a conversa existe e pertence a este utilizador."""
    with _conn() as conn:
        return conn.execute(
            f"SELECT 1 FROM conversations WHERE id = %s AND user_id = {USER_ID}",
            (conv_id, username),
        ).fetchone() is not None


def conversation_title(username: str, conv_id: int) -> str | None:
    """Título da conversa própria, ou ``None`` se não existir / não for dono."""
    with _conn() as conn:
        row = conn.execute(
            f"SELECT title FROM conversations WHERE id = %s AND user_id = {USER_ID}",
            (conv_id, username),
        ).fetchone()
    return row[0] if row else None


def add_message(
    conv_id: int, role: str, content: str,
    sql: str | None = None, kind: str | None = None, request_id: int | None = None,
    result: str | None = None,
) -> None:
    """Grava uma mensagem e atualiza ``updated_at`` da conversa.

    Args:
        conv_id: Id da conversa.
        role: ``user`` ou ``assistant``.
        content: Texto da mensagem.
        sql: SQL usado (só respostas com query), opcional.
        kind: ``sql``, ``forecast``, ``orders``, ``no_sql``, ``denied`` ou ``error``, opcional.
        request_id: Registo do pedido em ``request_log`` (para o 👍/👎), opcional.
        result: Dados mostrados na resposta (``result_payload``), opcional.
    """
    with _conn() as conn:
        conn.execute(
            "INSERT INTO messages (conversation_id, role, content, sql, kind, request_id, result) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)",
            (conv_id, role, content, sql, kind, request_id, result),
        )
        conn.execute(
            "UPDATE conversations SET updated_at = now() WHERE id = %s", (conv_id,),
        )


def add_exchange(
    conv_id: int, question: str, answer: str,
    sql: str | None = None, kind: str | None = None, request_id: int | None = None,
    result: str | None = None,
) -> None:
    """Grava a pergunta e a resposta numa só transação: ficam as duas ou nenhuma.

    Antes, eram dois ``add_message`` (duas transações): se a 2.ª falhasse (p.ex. um NaN
    nas linhas, que o ``jsonb`` recusa), a pergunta ficava na conversa sem resposta.
    """
    with _conn() as conn:
        conn.execute(
            "INSERT INTO messages (conversation_id, role, content) VALUES (%s, 'user', %s)",
            (conv_id, question),
        )
        conn.execute(
            "INSERT INTO messages (conversation_id, role, content, sql, kind, request_id, result) "
            "VALUES (%s, 'assistant', %s, %s, %s, %s, %s::jsonb)",
            (conv_id, answer, sql, kind, request_id, result),
        )
        conn.execute("UPDATE conversations SET updated_at = now() WHERE id = %s", (conv_id,))


def get_history(conv_id: int, turns: int = 3) -> list[tuple[str, str]]:
    """Últimas trocas (pergunta, SQL ou etiqueta) para dar contexto ao LLM."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT role, content, sql, kind FROM messages WHERE conversation_id = %s "
            "ORDER BY id DESC LIMIT %s", (conv_id, turns * 2),
        ).fetchall()
    rows.reverse()
    return build_history(rows)


def build_history(rows: list[tuple]) -> list[tuple[str, str]]:
    """Converte linhas ``(role, content, sql, kind)`` em pares para o prompt.

    Cada pergunta de utilizador fica associada à resposta seguinte:
    o SQL real, ou a etiqueta ``FORECAST`` / ``ORDERS`` / ``NO_SQL``.
    Trocas que falharam (``kind='error'``) ficam de fora: o LLM não deve
    tomar um SQL partido como exemplo a seguir.
    """
    history, question = [], None
    for role, content, sql, kind in rows:
        if role == "user":
            question = content
        elif question and kind == "error":
            question = None
        elif question:
            reply = sql or {"forecast": "FORECAST", "orders": "ORDERS"}.get(kind, "NO_SQL")
            history.append((question, reply))
            question = None
    return history


def rename_conversation(username: str, conv_id: int, title: str) -> bool:
    """Renomeia conversa própria. Devolve False se não existir / não for dono."""
    with _conn() as conn:
        cur = conn.execute(
            f"UPDATE conversations SET title = %s WHERE id = %s AND user_id = {USER_ID}",
            (title.strip(), conv_id, username),
        )
        return cur.rowcount > 0


def delete_conversation(username: str, conv_id: int) -> bool:
    """Apaga conversa própria. Devolve False se não existir / não for dono."""
    with _conn() as conn:
        cur = conn.execute(
            f"DELETE FROM conversations WHERE id = %s AND user_id = {USER_ID}",
            (conv_id, username),
        )
        return cur.rowcount > 0


def sql_of_request(username: str, request_id: int) -> str | None:
    """SQL de uma resposta da própria conta (``None`` se não existir ou não for dela)."""
    with _conn() as conn:
        row = conn.execute(
            f"""SELECT m.sql FROM messages m JOIN conversations c ON c.id = m.conversation_id
                WHERE m.request_id = %s AND c.user_id = {USER_ID} AND m.sql IS NOT NULL""",
            (request_id, username),
        ).fetchone()
    return row[0] if row else None
