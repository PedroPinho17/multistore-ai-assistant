"""Pools de ligações à BD partilhados pela API (psycopg_pool).

Abrir uma ligação Postgres custa vários milissegundos (TCP + autenticação
SCRAM). Cada pedido ao ``/ask`` usa 5–8 ligações (utilizador, RAG, RLS,
conversa, registo), por isso a API reutiliza ligações já abertas.

Há dois pools:

- ``owner``: ``DATABASE_URL`` (tabelas privadas: users, conversas, registo).
- ``readonly``: ``READONLY_DATABASE_URL`` (role ``assistente``, SQL do LLM).
  Cada ligação nasce ``read_only``. O contexto RLS é definido com
  ``set_config(..., true)``, que só vale para a transação: quando a ligação
  volta ao pool já não leva o perfil do pedido anterior.

Os scripts offline (gerar dados, treinar, avaliar) continuam a usar
``psycopg.connect``: correm uma vez e terminam.
"""
import atexit
import os
import threading

from psycopg import Connection
from psycopg_pool import ConnectionPool

MIN_SIZE = 1
MAX_SIZE = int(os.getenv("DB_POOL_MAX", "10"))
TIMEOUT = 10          # segundos à espera de uma ligação livre antes de dar erro

_URLS = {"owner": "DATABASE_URL", "readonly": "READONLY_DATABASE_URL"}
_pools: dict[str, ConnectionPool] = {}
_lock = threading.Lock()


def _configure_readonly(conn: Connection) -> None:
    """Defesa extra além do default do role: a ligação não consegue escrever."""
    conn.read_only = True


def get_pool(kind: str = "owner") -> ConnectionPool:
    """Pool ``owner`` ou ``readonly``, criado no 1.º uso (lê o URL nessa altura)."""
    pool = _pools.get(kind)
    if pool is None:
        with _lock:
            pool = _pools.get(kind)
            if pool is None:
                pool = ConnectionPool(
                    os.environ[_URLS[kind]],
                    min_size=MIN_SIZE, max_size=MAX_SIZE, timeout=TIMEOUT,
                    configure=_configure_readonly if kind == "readonly" else None,
                    # Se o Postgres reiniciou, a ligação morta é trocada antes de ser usada
                    check=ConnectionPool.check_connection,
                    name=f"multistore-{kind}", open=True,
                )
                _pools[kind] = pool
    return pool


def connection(kind: str = "owner"):
    """Context manager: ``with connection() as conn:`` (commit no fim, rollback se falhar)."""
    return get_pool(kind).connection()


def close_pools() -> None:
    """Fecha todos os pools (fim da aplicação ou dos testes)."""
    with _lock:
        for pool in _pools.values():
            pool.close()
        _pools.clear()


atexit.register(close_pools)
