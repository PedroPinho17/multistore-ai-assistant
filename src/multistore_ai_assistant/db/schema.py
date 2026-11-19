"""Lê o esquema da BD e transforma-o em texto para o prompt do LLM.

Usa a ligação read-only para listar só o que o role ``assistente`` vê
(sem ``users``, ``app_secret`` nem colunas pessoais). Os valores exactos
das colunas de categoria (métodos de pagamento, etc.) vêm da ligação dono,
porque o RLS sem contexto devolveria listas vazias.
"""
import time

from dotenv import load_dotenv

from multistore_ai_assistant.db.pool import connection

load_dotenv()

COLUMNS_SQL = """
SELECT c.table_name, c.column_name, c.data_type
FROM information_schema.columns c
JOIN information_schema.tables t
  ON t.table_name = c.table_name AND t.table_schema = c.table_schema
WHERE c.table_schema = 'public' AND t.table_type IN ('BASE TABLE', 'VIEW')
ORDER BY c.table_name, c.ordinal_position
"""

FKS_SQL = """
SELECT c.conrelid::regclass::text, a.attname,
       c.confrelid::regclass::text, af.attname
FROM pg_constraint c
JOIN pg_attribute a  ON a.attrelid = c.conrelid  AND a.attnum = c.conkey[1]
JOIN pg_attribute af ON af.attrelid = c.confrelid AND af.attnum = c.confkey[1]
WHERE c.contype = 'f' AND c.connamespace = 'public'::regnamespace
"""

CATEGORY_COLUMNS = [
    ("sales", "payment_method"),
    ("purchases", "status"),
    ("products", "category"),
    ("stores", "store_type"),
    ("employees", "role"),
    ("employees", "contract_type"),
]


def get_value_hints(conn) -> str:
    """Valores possíveis das colunas de categoria (ex.: ``'mbway'``, ``'recebida'``).

    Usa a ligação de dono: com o role ``assistente`` e sem perfil, o RLS
    devolvia listas vazias. São só etiquetas, não dados sensíveis.
    """
    lines = []
    for table, column in CATEGORY_COLUMNS:
        rows = conn.execute(
            f"SELECT DISTINCT {column} FROM {table} ORDER BY 1 LIMIT 20"
        ).fetchall()
        values = ", ".join(f"'{r[0]}'" for r in rows)
        lines.append(f"- {table}.{column}: {values}")
    return "Exact values of category columns:\n" + "\n".join(lines)


CACHE_SECONDS = 600
_cache: dict[str, tuple[float, str]] = {}


def get_schema_text() -> str:
    """Schema para o prompt, em cache ~10 min (igual em todas as perguntas)."""
    hit = _cache.get("schema")
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    text = _build_schema_text()
    _cache["schema"] = (time.monotonic(), text)
    return text


def _build_schema_text() -> str:
    """Monta ``tabela(col tipo -> fk, …)`` + hints de valores de categoria."""
    # Tabelas e colunas vistas pelo role 'assistente': o LLM não fica a saber
    # que existem users, app_secret, conversas ou colunas de dados pessoais
    with connection("readonly") as conn:
        columns = conn.execute(COLUMNS_SQL).fetchall()
        fks = conn.execute(FKS_SQL).fetchall()

        fk_map = {(t, c): f"{rt}.{rc}" for t, c, rt, rc in fks}
        tables: dict[str, list[str]] = {}
        for table, column, dtype in columns:
            col = f"{column} {dtype}"
            if (table, column) in fk_map:
                col += f" -> {fk_map[(table, column)]}"
            tables.setdefault(table, []).append(col)

        schema_text = "\n".join(f"{t}({', '.join(cols)})" for t, cols in tables.items())
    with connection("owner") as owner:
        return schema_text + "\n\n" + get_value_hints(owner)


if __name__ == "__main__":
    print(get_schema_text())
