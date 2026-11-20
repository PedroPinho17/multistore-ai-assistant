"""Valida o SQL gerado pelo LLM antes de o correr na BD.

Só aceita uma única query de leitura (SELECT / WITH … SELECT). Bloqueia DML/DDL,
tabelas de sistema, tabelas sensíveis e funções que alterem a sessão ou leiam
ficheiros / abram ligações. A defesa real de dados continua a ser o RLS + role
read-only; isto é a primeira barreira no AST (sqlglot).
"""
import sqlglot
from sqlglot import exp

FORBIDDEN = (
    exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Command,
    exp.Into, exp.Lock, exp.Merge, exp.Alter, exp.TruncateTable,
)
BLOCKED_PREFIXES = ("pg_", "information_schema")
BLOCKED_TABLES = {"users", "app_secret"}

# Funções que mudam o contexto da sessão, executam SQL dentro de uma string,
# leem ficheiros ou falam com outros servidores.
BLOCKED_FUNCTIONS = {
    "set_config", "current_setting", "dblink", "dblink_exec",
    "query_to_xml", "query_to_xmlschema", "query_to_xml_and_xmlschema",
    "cursor_to_xml", "cursor_to_xmlschema",
    "hmac", "digest", "crypt", "gen_salt", "encrypt", "decrypt",
}
BLOCKED_FUNCTION_PREFIXES = (
    "pg_", "lo_", "dblink", "table_to_xml", "schema_to_xml",
    "database_to_xml", "txid_",
)
MAX_SQL_LENGTH = 10_000

# Colunas ``timestamp`` (sem fuso) das tabelas que o assistente lê. Comparadas com uma
# data (``sold_at >= CAST('2026-01-01' AS DATE)``) usam o operador timestamp/date, que
# NÃO é leakproof: com RLS ativo o Postgres deixa então de usar as estatísticas da coluna,
# estima 1 linha e escolhe planos que passam o statement_timeout (perguntas 16 e 27 do
# eval: > 30 s em vez de 0,3 s). Com timestamp/timestamp (leakproof) o plano é normal.
# Tem de coincidir com a BD: tests/integration/test_rls_performance.py confirma-o.
TIMESTAMP_COLUMNS = frozenset({"sold_at", "updated_at"})
COMPARISONS = (exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE)
TIMESTAMP = exp.DataType.build("timestamp")


class InvalidSQL(Exception):
    """SQL rejeitado pelo validador (mensagem segura para devolver ao cliente)."""


def _function_name(node: exp.Func) -> str:
    """Nome da função em minúsculas (inclui funções anónimas / custom)."""
    if isinstance(node, exp.Anonymous):
        return str(node.name).lower()
    return node.sql_name().lower()


def _is_timestamp_column(node: exp.Expression) -> bool:
    return isinstance(node, exp.Column) and node.name.lower() in TIMESTAMP_COLUMNS


def _as_timestamp(node: exp.Expression) -> exp.Expression:
    """A mesma expressão como ``timestamp`` (o que o Postgres já faria implicitamente)."""
    if isinstance(node, exp.Cast) and node.to.is_type("timestamp"):
        return node
    if isinstance(node, exp.Cast) and node.to.is_type("date") and isinstance(node.this, exp.Literal):
        return exp.Cast(this=node.this.copy(), to=TIMESTAMP.copy())   # CAST('…' AS DATE) → AS TIMESTAMP
    return exp.Cast(this=node.copy(), to=TIMESTAMP.copy())           # CURRENT_DATE, DATE_TRUNC(…), '…'


def timestamp_comparisons(query: exp.Expression) -> exp.Expression:
    """Compara as colunas ``timestamp`` com valores ``timestamp`` (ver TIMESTAMP_COLUMNS).

    Só muda o tipo do outro lado da comparação, para o mesmo valor que o Postgres
    usaria (uma data passa a essa data às 00:00): o resultado da query não muda.
    """
    for node in list(query.find_all(*COMPARISONS)):
        left, right = node.left, node.right
        if _is_timestamp_column(left) and not isinstance(right, exp.Column):
            node.set("expression", _as_timestamp(right))
        elif _is_timestamp_column(right) and not isinstance(left, exp.Column):
            node.set("this", _as_timestamp(left))
    for node in list(query.find_all(exp.Between)):
        if _is_timestamp_column(node.this):
            for side in ("low", "high"):
                if not isinstance(node.args[side], exp.Column):
                    node.set(side, _as_timestamp(node.args[side]))
    return query


def widen_ilike(sql: str) -> str | None:
    """``x ILIKE 'Maia'`` → ``x ILIKE '%Maia%'``; ``None`` se não houver nada a alargar.

    Para quando um filtro por nome sem ``%`` devolve 0 linhas (o nome na BD é
    "BurgerLab Maia"). Não toca em padrões que já têm ``%``, em padrões vazios
    (``'%%'`` apanhava tudo) nem em filtros negados (``NOT ILIKE``, ``NOT (…)``,
    ``NOT EXISTS``): aí alargar devolveria *menos* linhas, não mais.
    O resultado tem de passar outra vez por ``validate_sql``.
    """
    try:
        query = sqlglot.parse_one(sql, read="postgres")
    except sqlglot.errors.ParseError:
        return None
    changed = False
    for node in list(query.find_all(exp.ILike)):
        pattern = node.expression
        if (node.args.get("negate") or node.find_ancestor(exp.Not)
                or not isinstance(pattern, exp.Literal) or not pattern.is_string
                or not pattern.this or "%" in pattern.this):
            continue
        node.set("expression", exp.Literal.string(f"%{pattern.this}%"))
        changed = True
    return query.sql(dialect="postgres") if changed else None


def validate_sql(sql: str) -> str:
    """Parseia e valida o SQL; devolve a forma canónica em dialecto Postgres.

    Args:
        sql: Texto gerado pelo LLM (já sem fences).

    Returns:
        SQL normalizado pronto a executar.

    Raises:
        InvalidSQL: mais do que uma statement, escrita, tabela/função bloqueada, etc.
    """
    if len(sql) > MAX_SQL_LENGTH:
        raise InvalidSQL("SQL demasiado longo.")
    try:
        statements = sqlglot.parse(sql, read="postgres")
    except sqlglot.errors.ParseError as e:
        raise InvalidSQL(f"SQL inválido: {e}") from e

    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        raise InvalidSQL("Só é permitida uma query.")

    query = statements[0]
    if not isinstance(query, exp.Query):
        raise InvalidSQL("Só são permitidas queries SELECT.")

    if any(query.find_all(*FORBIDDEN)):
        raise InvalidSQL("A query contém operações de escrita.")

    for func in query.find_all(exp.Func):
        name = _function_name(func)
        if name in BLOCKED_FUNCTIONS or name.startswith(BLOCKED_FUNCTION_PREFIXES):
            raise InvalidSQL(f"Função não permitida: {name}")

    for table in query.find_all(exp.Table):
        names = {str(table.db).lower(), str(table.name).lower()}
        if any(n.startswith(BLOCKED_PREFIXES) for n in names) or names & BLOCKED_TABLES:
            raise InvalidSQL(f"Acesso não permitido: {table.sql()}")

    return timestamp_comparisons(query).sql(dialect="postgres")
