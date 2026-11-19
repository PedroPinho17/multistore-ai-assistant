"""Gestão dos exemplos do RAG (página "Ensinar" → Exemplos, módulo ``teach``).

Os exemplos pergunta → SQL entram no prompt de **todas** as contas quando uma
pergunta parecida aparece (``assistant.examples.find_similar``). Um exemplo
errado piora as respostas de toda a gente; um exemplo que nunca é usado só
ocupa espaço. Esta página serve para:

- ver o que o assistente aprendeu, de onde veio (instalação, chat, revisão de 👎,
  manual), quem o ensinou e **quantas vezes já foi usado**;
- corrigir o SQL ou a pergunta (com as mesmas regras do ``/feedback``:
  validador + ``EXPLAIN``), testando antes com o RLS de quem edita;
- apagar exemplos errados ou duplicados;
- criar um exemplo novo para um tipo de pergunta que o assistente falha.
"""
from multistore_ai_assistant.api.errors import ApiError
from multistore_ai_assistant.api.review import teachable_sql
from multistore_ai_assistant.assistant.examples import embed
from multistore_ai_assistant.db.pool import connection

COLUMNS = ("id", "question", "sql", "source", "created_at", "created_by", "updated_at", "updated_by",
           "uses", "last_used_at")


def list_examples() -> list[dict]:
    """Todos os exemplos, os mais usados primeiro."""
    with connection("owner") as conn:
        rows = conn.execute(f"""SELECT {", ".join(COLUMNS)} FROM sql_examples
                                ORDER BY uses DESC, created_at DESC""").fetchall()
    out = []
    for r in rows:
        item = dict(zip(COLUMNS, r, strict=True))
        for k in ("created_at", "updated_at", "last_used_at"):
            item[k] = item[k].isoformat() if item[k] else None
        out.append(item)
    return out


def _question_taken(conn, question: str, except_id: int | None = None) -> bool:
    row = conn.execute("SELECT id FROM sql_examples WHERE lower(question) = lower(%s)", (question,)).fetchone()
    return row is not None and row[0] != except_id


def create(question: str, sql: str, user: dict) -> int:
    """Exemplo novo (``source = manual``). Recusa uma pergunta que já exista (não a substitui às escondidas)."""
    question = question.strip()
    sql = teachable_sql(sql, user)
    with connection("owner") as conn:
        if _question_taken(conn, question):
            raise ApiError("example_exists", 409)
        return conn.execute(
            """INSERT INTO sql_examples (question, sql, embedding, source, created_by)
               VALUES (%s, %s, %s::vector, 'manual', %s) RETURNING id""",
            (question, sql, embed(question), user["username"])).fetchone()[0]


def update(example_id: int, question: str, sql: str, user: dict) -> None:
    """Corrige pergunta e/ou SQL; o embedding é recalculado (a pergunta é o que o RAG compara)."""
    question = question.strip()
    sql = teachable_sql(sql, user)
    with connection("owner") as conn:
        if _question_taken(conn, question, except_id=example_id):
            raise ApiError("example_exists", 409)
        cur = conn.execute(
            """UPDATE sql_examples SET question = %s, sql = %s, embedding = %s::vector,
                      updated_at = now(), updated_by = %s
               WHERE id = %s""",
            (question, sql, embed(question), user["username"], example_id))
        if cur.rowcount == 0:
            raise ApiError("example_not_found", 404)


def delete(example_id: int) -> None:
    with connection("owner") as conn:
        if conn.execute("DELETE FROM sql_examples WHERE id = %s", (example_id,)).rowcount == 0:
            raise ApiError("example_not_found", 404)
