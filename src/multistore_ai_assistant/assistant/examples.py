"""RAG de exemplos pergunta → SQL com embeddings (pgvector).

Os exemplos validados (seed + feedback do Imperador) são guardados com o
embedding MiniLM multilingue. Na geração de SQL, os k mais próximos entram
no prompt se a distância coseno for ≤ ``MAX_DISTANCE``.
"""
import logging
from functools import lru_cache

from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

from multistore_ai_assistant.db.pool import connection

load_dotenv()
log = logging.getLogger("multistore")

# Modelo multilingue (PT e EN), 384 dimensões
MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
MAX_DISTANCE = 0.6  # 0 = igual, 2 = oposto (<=> em pgvector com embeddings normalizados)


@lru_cache
def _model() -> SentenceTransformer:
    """Carrega o modelo de embeddings uma única vez por processo."""
    return SentenceTransformer(MODEL_NAME)


def embed(text: str) -> str:
    """Converte texto no literal ``[x,y,…]`` aceite pelo tipo ``vector`` do Postgres."""
    vector = _model().encode(text, normalize_embeddings=True)
    return "[" + ",".join(f"{x:.6f}" for x in vector) + "]"


def add_example(question: str, sql: str, source: str = "seed", created_by: str | None = None, conn=None) -> None:
    """Insere ou actualiza um exemplo na tabela ``sql_examples``.

    Args:
        question: Pergunta canónica (chave única). Se já existir, o SQL é substituído.
        sql: SELECT validado.
        source: Origem (``seed``, ``feedback``, ``review``, ``manual``).
        created_by: Conta que o ensinou (``None`` nos exemplos da instalação).
        conn: Ligação já aberta (para gravar na mesma transação que outra escrita).
    """
    if conn is None:
        with connection("owner") as own:
            add_example(question, sql, source, created_by, conn=own)
        return
    conn.execute(
        """INSERT INTO sql_examples (question, sql, embedding, source, created_by)
           VALUES (%s, %s, %s::vector, %s, %s)
           ON CONFLICT (question) DO UPDATE
           SET sql = EXCLUDED.sql, embedding = EXCLUDED.embedding, source = EXCLUDED.source,
               updated_at = now(), updated_by = EXCLUDED.created_by""",
        (question, sql, embed(question), source, created_by),
    )


def record_use(questions: list[str]) -> None:
    """Conta os exemplos que entraram num prompt (falhar aqui nunca afeta a resposta)."""
    if not questions:
        return
    try:
        with connection("owner") as conn:
            conn.execute("UPDATE sql_examples SET uses = uses + 1, last_used_at = now() WHERE question = ANY(%s)",
                         (questions,))
    except Exception:
        log.warning("Não foi possível contar o uso dos exemplos", exc_info=True)


def find_similar(question: str, k: int = 3) -> list[tuple[str, str]]:
    """Devolve até ``k`` exemplos próximos com distância ≤ ``MAX_DISTANCE``.

    Usa a ligação read-only (só SELECT em ``sql_examples``).
    """
    with connection("readonly") as conn:
        rows = conn.execute(
            """SELECT question, sql, embedding <=> %s::vector AS distance
               FROM sql_examples ORDER BY distance LIMIT %s""",
            (embed(question), k),
        ).fetchall()
    found = [(q, s) for q, s, d in rows if d <= MAX_DISTANCE]
    record_use([q for q, _ in found])
    return found


if __name__ == "__main__":
    for q, s in find_similar("How many ice creams did each kiosk sell last summer?"):
        print(q, "\n ", s, "\n")
