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


class InvalidSQL(Exception):
    """SQL rejeitado pelo validador (mensagem segura para devolver ao cliente)."""


def _function_name(node: exp.Func) -> str:
    """Nome da função em minúsculas (inclui funções anónimas / custom)."""
    if isinstance(node, exp.Anonymous):
        return str(node.name).lower()
    return node.sql_name().lower()


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

    return query.sql(dialect="postgres")
