"""Executa SELECT com o role read-only e contexto RLS assinado.

Antes de correr a query, define ``app.role``, ``app.brand_id``, ``app.store_id``
e ``app.sig`` (HMAC). As policies Postgres só confiam no role se a assinatura
bater com a chave em ``app_secret`` (inacessível ao role ``assistente``).

As ligações vêm do pool ``readonly`` (``db.pool``). Como o contexto é
definido com ``set_config(..., true)``, só vale para esta transação e não
passa para o pedido seguinte que reutilizar a ligação.
"""
import hashlib
import hmac
from functools import lru_cache

from dotenv import load_dotenv

from multistore_ai_assistant.db.pool import connection

load_dotenv()

MAX_ROWS = 500
STATEMENT_TIMEOUT = "10s"
IMPERADOR = {"role": "imperador", "brand_id": None, "store_id": None}


@lru_cache
def _rls_key() -> str:
    """Chave HMAC guardada na BD (o role ``assistente`` não a consegue ler)."""
    with connection("owner") as conn:
        row = conn.execute("SELECT key FROM app_secret WHERE id = 1").fetchone()
    if not row:
        raise RuntimeError("Falta a chave em app_secret: corre as migrações (python -m multistore_ai_assistant.db.migrate).")
    return row[0]


def _context(user: dict) -> tuple[str, str, str, str]:
    """Constrói (role, brand_id, store_id, assinatura) para ``set_config``.

    A assinatura impede que SQL hostil faça ``set_config('app.role','imperador')``
    e veja todos os dados: sem ``app.sig`` válido o RLS devolve zero linhas.
    O admin entra nas policies como ``imperador`` (o RLS só conhece 3 perfis).
    """
    role = "imperador" if user["role"] == "admin" else user["role"]
    brand = str(user["brand_id"] or "")
    store = str(user["store_id"] or "")
    message = f"{role}|{brand}|{store}".encode()
    sig = hmac.new(_rls_key().encode(), message, hashlib.sha256).hexdigest()
    return role, brand, store, sig


def run_query(sql: str, user: dict) -> tuple[list[str], list[tuple]]:
    """Corre um SELECT validado sob o perfil do utilizador.

    Args:
        sql: Query já validada por ``validate_sql``.
        user: Perfil com ``role`` / ``brand_id`` / ``store_id``. Obrigatório:
            esquecer o utilizador não pode dar acesso a tudo. Scripts offline
            passam ``IMPERADOR`` explicitamente.

    Returns:
        ``(nomes_das_colunas, linhas)`` — no máximo ``MAX_ROWS`` linhas.
    """
    if not user or not user.get("role"):
        raise ValueError("run_query precisa do perfil do utilizador (role).")
    with connection("readonly") as conn, conn.cursor() as cur:   # ligação read_only (ver db.pool)
        # true = só vale para esta transação
        cur.execute(
            "SELECT set_config('statement_timeout', %s, true),"
            " set_config('app.role', %s, true),"
            " set_config('app.brand_id', %s, true),"
            " set_config('app.store_id', %s, true),"
            " set_config('app.sig', %s, true)",
            (STATEMENT_TIMEOUT, *_context(user)),
        )
        cur.execute(sql)
        columns = [c.name for c in cur.description]
        rows = cur.fetchmany(MAX_ROWS)
    return columns, rows
