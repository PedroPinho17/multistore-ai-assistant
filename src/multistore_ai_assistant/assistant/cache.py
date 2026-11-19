"""Cache de SQL por pergunta: reaproveita o SQL de uma pergunta que pede os mesmos dados.

Duas fases:

1. **Candidatos pelo embedding** (MiniLM multilingue, o mesmo do RAG): as
   ``CANDIDATES`` perguntas mais próximas feitas hoje no mesmo perfil, até
   ``MAX_DISTANCE``. Encontra reformulações e outras línguas, mas não decide.
2. **Decisão pela chave normalizada** (``question_key``): sinónimos nas 4
   línguas, agrupamentos, períodos, ordem e palavras desconhecidas têm de bater.

Porque não chega a distância: medido em ``eval/cache_pairs.json``, reformulações
com o mesmo significado ficam a 0,003–0,31 e perguntas diferentes a partir de
0,016 ("outubro" vs "novembro", "mais" vs "menos"). Com um limiar só de distância,
ou se reaproveita SQL errado ou quase nunca se acerta. Na parte de teste do
conjunto (escrita depois do léxico), a chave junta 19/20 reformulações e 0/20
perguntas diferentes.

Segurança e frescura:

- o SQL **corre sempre de novo** com o contexto RLS de quem pergunta: a cache
  guarda SQL, nunca resultados;
- o âmbito é o perfil de dados (imperador / marca / loja);
- só vale no próprio dia (o LLM recebe a data de hoje e pode escrever datas
  literais para "ontem" ou "este mês");
- conversas com histórico não usam a cache ("e no Porto?" depende do contexto).
"""
import logging

from multistore_ai_assistant.api.permissions import data_role
from multistore_ai_assistant.assistant.examples import embed
from multistore_ai_assistant.assistant.question_key import question_key
from multistore_ai_assistant.db.pool import connection

log = logging.getLogger("multistore")
MAX_DISTANCE = 0.35        # só para candidatos: reformulações medidas chegam a 0,31
CANDIDATES = 20
TZ = "Europe/Lisbon"


def scope_of(user: dict) -> str:
    """Âmbito da cache: o perfil que o RLS conhece."""
    return data_role(user["role"])


def lookup(question: str, user: dict) -> dict | None:
    """SQL de uma pergunta com a mesma chave, feita hoje no mesmo âmbito, ou ``None``."""
    try:
        with connection("owner") as conn:
            row = conn.execute(
                f"""SELECT id, question, sql, embedding <=> %s::vector AS distance
                    FROM query_cache
                    WHERE scope = %s AND (created_at AT TIME ZONE '{TZ}')::date = (now() AT TIME ZONE '{TZ}')::date
                    ORDER BY distance LIMIT {CANDIDATES}""",
                (embed(question), scope_of(user)),
            ).fetchall()
            wanted = question_key(question)
            row = next((r for r in row if r[3] <= MAX_DISTANCE and question_key(r[1]) == wanted), None)
            if row is None:
                return None
            conn.execute("UPDATE query_cache SET hits = hits + 1, last_hit_at = now() WHERE id = %s", (row[0],))
        return {"id": row[0], "question": row[1], "sql": row[2], "distance": float(row[3])}
    except Exception:
        log.warning("Cache de SQL indisponível", exc_info=True)
        return None


def store(question: str, sql: str, user: dict) -> None:
    """Guarda o SQL que respondeu a uma pergunta (falhar aqui nunca afeta a resposta)."""
    try:
        with connection("owner") as conn:
            conn.execute(
                "INSERT INTO query_cache (scope, question, embedding, sql) VALUES (%s, %s, %s::vector, %s)",
                (scope_of(user), question, embed(question), sql),
            )
    except Exception:
        log.warning("Não foi possível guardar na cache de SQL", exc_info=True)
