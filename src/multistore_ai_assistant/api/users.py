"""Gestão de contas: listar, criar, alterar módulos/estado/password e apagar.

As regras (quem pode criar o quê, quem gere quem) estão em ``permissions``;
aqui só se lê e grava na BD. Quem atua vem sempre do token (``current_user``),
nunca de um campo enviado pelo cliente.
"""
import re

import bcrypt
import psycopg

from multistore_ai_assistant.api.permissions import (
    MAX_CREATED_PER_USER,
    MODULES,
    NEW_ACCOUNT_MODULES,
    ROLE_LEVEL,
    ROLE_MODULES,
    ROLES,
    AccessDenied,
    can_manage,
    can_view,
    check_modules,
    check_new_account,
    effective_modules,
    in_scope,
    is_demo,
    require_not_demo,
)
from multistore_ai_assistant.api.profile import PasswordError, check_new_password
from multistore_ai_assistant.db.pool import connection

USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,32}$")

SELECT_USERS = """
    SELECT u.id, u.username, u.role, u.brand_id, u.store_id, s.brand_id AS store_brand,
           u.modules, u.active, u.protected, u.created_by, c.username AS created_by_name,
           u.created_at, u.last_login, coalesce(b.name, sb.name) AS brand_name, s.name AS store_name,
           u.avatar
    FROM users u
    LEFT JOIN stores s  ON s.id = u.store_id
    LEFT JOIN brands b  ON b.id = u.brand_id
    LEFT JOIN brands sb ON sb.id = s.brand_id
    LEFT JOIN users c   ON c.id = u.created_by
"""


def _row_to_user(cur, row) -> dict:
    """Linha de ``SELECT_USERS`` → dict (módulos efetivos, datas em ISO)."""
    u = dict(zip([c.name for c in cur.description], row, strict=False))
    u["modules"] = effective_modules(u["role"], u["modules"])
    for k in ("created_at", "last_login"):
        u[k] = u[k].isoformat() if u[k] else None
    return u


def _password_ok(username: str, password: str) -> None:
    """Mesmas regras da página de perfil (≥ 8, letras e números, sem o username)."""
    try:
        check_new_password(username, "", password)
    except PasswordError as e:
        raise AccessDenied(e.code, str(e), 400, **e.params) from None


def _get(conn, user_id: int) -> dict | None:
    cur = conn.execute(SELECT_USERS + " WHERE u.id = %s", (user_id,))
    row = cur.fetchone()
    return _row_to_user(cur, row) if row else None


def list_users(actor: dict) -> list[dict]:
    """Contas que quem atua pode ver, com ``can_manage`` para a UI saber o que mostrar."""
    with connection("owner") as conn:
        cur = conn.execute(SELECT_USERS + " ORDER BY u.created_at, u.id")
        users = [_row_to_user(cur, r) for r in cur.fetchall()]
    out = []
    for u in users:
        if can_view(actor, u):
            u["can_manage"] = can_manage(actor, u)
            u["is_me"] = u["id"] == actor["id"]
            out.append(u)
    return out


def options(actor: dict) -> dict:
    """O que o formulário de nova conta pode oferecer a quem atua."""
    roles = [r for r in ROLES if ROLE_LEVEL[r] >= ROLE_LEVEL[actor["role"]]]
    mine = set(actor["modules"])
    with connection("owner") as conn:
        brands = conn.execute("SELECT id, name FROM brands ORDER BY name").fetchall()
        stores = conn.execute("SELECT id, name, brand_id FROM stores ORDER BY name").fetchall()
    brands = [{"id": i, "name": n} for i, n in brands
              if in_scope(actor, "marca", i, None, None)]
    stores = [{"id": i, "name": n, "brand_id": b} for i, n, b in stores
              if in_scope(actor, "loja", None, b, i)]
    if actor["role"] == "loja":        # uma loja não cria contas de marca
        brands = []
    return {
        "read_only": is_demo(actor),
        "roles": [r for r in roles if r != "marca" or brands],
        "brands": brands,
        "stores": stores,
        "modules": {r: [m for m in MODULES if m in ROLE_MODULES[r] & mine] for r in roles},
        "defaults": {r: [m for m in MODULES if m in NEW_ACCOUNT_MODULES & ROLE_MODULES[r] & mine] for r in roles},
    }


def create_user(actor: dict, username: str, password: str, role: str,
                brand_id: int | None = None, store_id: int | None = None,
                modules: list[str] | None = None) -> dict:
    """Cria uma conta do mesmo nível ou abaixo, dentro do âmbito de quem atua."""
    require_not_demo(actor)
    username = username.strip().lower()
    if not USERNAME_RE.match(username):
        raise AccessDenied("bad_username", "Nome de utilizador inválido (3–32: letras, números, . _ -).", 400)
    _password_ok(username, password)
    with connection("owner") as conn:
        store_brand = None
        if store_id:
            row = conn.execute("SELECT brand_id FROM stores WHERE id = %s", (store_id,)).fetchone()
            if not row:
                raise AccessDenied("need_store", "Loja inexistente.", 400)
            store_brand = row[0]
        if brand_id and not conn.execute("SELECT 1 FROM brands WHERE id = %s", (brand_id,)).fetchone():
            raise AccessDenied("need_brand", "Marca inexistente.", 400)
        final_modules = check_new_account(actor, role, brand_id, store_id, store_brand, modules)
        created = conn.execute("SELECT count(*) FROM users WHERE created_by = %s", (actor["id"],)).fetchone()[0]
        if created >= MAX_CREATED_PER_USER and actor["role"] != "admin":
            raise AccessDenied("too_many_users", f"Limite de {MAX_CREATED_PER_USER} contas criadas.", 429,
                               n=MAX_CREATED_PER_USER)
        hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        try:
            new_id = conn.execute(
                """INSERT INTO users (username, password_hash, role, brand_id, store_id, modules, created_by)
                   VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id""",
                (username, hashed, role, brand_id or None, store_id or None, final_modules, actor["id"]),
            ).fetchone()[0]
        except psycopg.errors.UniqueViolation:
            raise AccessDenied("username_taken", "Esse nome de utilizador já existe.", 409) from None
        return _get(conn, new_id)


def _target(conn, actor: dict, user_id: int) -> dict:
    """Conta-alvo que quem atua pode gerir (404 se não a pode ver, 403 se só a vê)."""
    target = _get(conn, user_id)
    if not target or not can_view(actor, target):
        raise AccessDenied("not_found", "Utilizador não encontrado.", 404)
    require_not_demo(actor)
    if not can_manage(actor, target):
        raise AccessDenied("cannot_manage", "Não podes alterar esta conta.")
    return target


def update_user(actor: dict, user_id: int, modules: list[str] | None = None,
                active: bool | None = None, password: str | None = None) -> dict:
    """Altera módulos, estado (ativa/desativada) e/ou repõe a password."""
    require_not_demo(actor)
    with connection("owner") as conn:
        target = _target(conn, actor, user_id)
        if modules is not None:
            final = check_modules(actor, target["role"], modules)
            conn.execute("UPDATE users SET modules = %s WHERE id = %s", (final, user_id))
        if active is not None:
            conn.execute("UPDATE users SET active = %s WHERE id = %s", (active, user_id))
        if password:
            _password_ok(target["username"], password)
            hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
            conn.execute("UPDATE users SET password_hash = %s WHERE id = %s", (hashed, user_id))
        return _get(conn, user_id)


def delete_user(actor: dict, user_id: int) -> None:
    """Apaga a conta (as conversas vão em cascata; o registo fica, sem o utilizador)."""
    require_not_demo(actor)
    with connection("owner") as conn:
        _target(conn, actor, user_id)
        conn.execute("DELETE FROM users WHERE id = %s", (user_id,))
