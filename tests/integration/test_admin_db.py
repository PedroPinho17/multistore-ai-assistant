"""Gestão de contas, registo de pedidos, painel admin e pool de ligações (BD real).

Todas as contas criadas aqui começam por ``pytest.`` e são apagadas no fim.
"""
import json
import os
from pathlib import Path

import psycopg
import pytest

from multistore_ai_assistant.api import admin, request_log, users
from multistore_ai_assistant.api.auth import authenticate, load_user
from multistore_ai_assistant.api.permissions import AccessDenied
from multistore_ai_assistant.data import create_admin
from multistore_ai_assistant.db import pool
from multistore_ai_assistant.db.query import run_query
from multistore_ai_assistant.observability import Trace

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[2]

try:
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=3) as _c:
        _ok = _c.execute("SELECT to_regclass('public.request_log') IS NOT NULL").fetchone()[0]
except Exception:
    _ok = False
if not _ok:
    pytest.skip("Base de dados indisponível ou sem a migração V005__admin.sql", allow_module_level=True)


def owner():
    return psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)


@pytest.fixture(autouse=True)
def cleanup():
    yield
    with owner() as c:
        c.execute("DELETE FROM request_log WHERE username LIKE 'pytest.%'")
        c.execute("DELETE FROM users WHERE username LIKE 'pytest.%' AND role <> 'admin'")
        c.execute("DELETE FROM users WHERE username LIKE 'pytest.%'")


@pytest.fixture(scope="module")
def maia():
    with owner() as c:
        return c.execute("SELECT s.id, s.brand_id FROM stores s WHERE s.name = 'BurgerLab Maia'").fetchone()


def actor(name):
    """Uma conta REAL com o perfil e o âmbito da conta de demo ``name``.

    As contas de demo só leem na gestão de contas (test_demo_accounts_db.py); aqui
    testam-se as regras de perfil/âmbito/módulos, por isso tira-se a marca de demo.
    """
    u = load_user(name)
    assert u, f"conta de demo {name} em falta (corre set_passwords)"
    return {**u, "protected": False}


# ---------- migração ----------

def test_admin_sql_is_idempotent():
    sql = (ROOT / "db" / "migrations" / "V005__admin.sql").read_text(encoding="utf-8")
    with owner() as c:
        c.execute(sql)
        c.execute(sql)
        protected = c.execute("SELECT count(*) FROM users WHERE protected AND username IN "
                              "('pedro','gestor.burgerlab','gerente.maia')").fetchone()[0]
    assert protected == 3


@pytest.mark.parametrize("bad", [
    "INSERT INTO users (username, role) VALUES ('pytest.x', 'loja')",                    # loja sem loja
    "INSERT INTO users (username, role, brand_id) VALUES ('pytest.x', 'imperador', 1)",  # imperador com marca
    "INSERT INTO users (username, role) VALUES ('Pytest X', 'imperador')",               # username inválido
    "INSERT INTO users (username, role) VALUES ('pytest.x', 'root')",
])
def test_database_constraints_back_up_the_rules(bad):
    with owner() as c, pytest.raises(psycopg.errors.CheckViolation):
        c.execute(bad)


def test_llm_role_cannot_read_the_request_log():
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        run_query("SELECT question FROM request_log", {"role": "imperador", "brand_id": None, "store_id": None})


# ---------- contas ----------

def test_brand_manager_creates_a_store_account_that_can_log_in(maia):
    store_id, brand_id = maia
    created = users.create_user(actor("gestor.burgerlab"), "pytest.loja", "Segura123", "loja",
                                store_id=store_id, modules=["sql", "forecast"])
    assert created["role"] == "loja" and created["store_brand"] == brand_id
    assert created["modules"] == ["sql", "forecast"] and created["created_by_name"] == "gestor.burgerlab"
    logged = authenticate("pytest.loja", "Segura123")
    assert logged["modules"] == ["sql", "forecast"] and logged["store_id"] == store_id


def test_store_manager_cannot_create_a_brand_account(maia):
    with pytest.raises(AccessDenied) as e:
        users.create_user(actor("gerente.maia"), "pytest.marca", "Segura123", "marca", brand_id=maia[1])
    assert e.value.code == "role_above"


def test_brand_manager_cannot_create_in_another_brand():
    with owner() as c:
        other = c.execute("SELECT id FROM stores WHERE brand_id <> 1 LIMIT 1").fetchone()[0]
    with pytest.raises(AccessDenied) as e:
        users.create_user(actor("gestor.burgerlab"), "pytest.fora", "Segura123", "loja", store_id=other)
    assert e.value.code == "out_of_scope"


def test_duplicate_username_and_weak_password(maia):
    me = actor("pedro")
    users.create_user(me, "pytest.dup", "Segura123", "imperador")
    with pytest.raises(AccessDenied) as e:
        users.create_user(me, "pytest.dup", "Segura123", "imperador")
    assert (e.value.code, e.value.status) == ("username_taken", 409)
    with pytest.raises(AccessDenied) as e:
        users.create_user(me, "pytest.fraca", "12345678", "imperador")
    assert e.value.code == "pw_mix"                          # só números


def test_disabling_an_account_blocks_login_and_existing_sessions(maia):
    me = actor("gestor.burgerlab")
    new = users.create_user(me, "pytest.temp", "Segura123", "loja", store_id=maia[0])
    users.update_user(me, new["id"], active=False)
    assert authenticate("pytest.temp", "Segura123") is None
    assert load_user("pytest.temp") is None                    # o token antigo deixa de valer
    users.update_user(me, new["id"], active=True, password="Nova-Pass-1")
    assert authenticate("pytest.temp", "Nova-Pass-1")


def test_modules_can_change_but_never_beyond_the_actor(maia):
    me = actor("gestor.burgerlab")
    new = users.create_user(me, "pytest.mods", "Segura123", "loja", store_id=maia[0])
    assert users.update_user(me, new["id"], modules=["orders"])["modules"] == ["orders"]
    with pytest.raises(AccessDenied):
        users.update_user(me, new["id"], modules=["sql", "teach"])


def test_demo_accounts_cannot_be_changed_by_other_demo_accounts():
    gerente = actor("gerente.maia")
    with pytest.raises(AccessDenied) as e:
        users.update_user(actor("pedro"), gerente["id"], active=False)
    assert e.value.code == "cannot_manage"
    assert load_user("gerente.maia")                            # continua ativa


def test_list_marks_what_can_be_managed(maia):
    me = actor("gestor.burgerlab")
    users.create_user(me, "pytest.lista", "Segura123", "loja", store_id=maia[0])
    listed = {u["username"]: u for u in users.list_users(me)}
    assert listed["pytest.lista"]["can_manage"] and not listed["gerente.maia"]["can_manage"]
    assert listed["gestor.burgerlab"]["is_me"] and "pedro" not in listed
    with owner() as c:
        other_store = c.execute("SELECT username FROM users WHERE role = 'loja' AND store_id IN "
                                "(SELECT id FROM stores WHERE brand_id <> 1)").fetchall()
    assert not {u for (u,) in other_store} & set(listed)


def test_hidden_accounts_are_404_not_403():
    with owner() as c:
        c.execute("INSERT INTO users (username, role) VALUES ('pytest.chefe', 'imperador')")
        uid = c.execute("SELECT id FROM users WHERE username = 'pytest.chefe'").fetchone()[0]
    with pytest.raises(AccessDenied) as e:
        users.delete_user(actor("gestor.burgerlab"), uid)
    assert e.value.status == 404


def test_deleting_an_account_removes_its_conversations(maia):
    from multistore_ai_assistant.api import conversations as conv
    me = actor("gestor.burgerlab")
    new = users.create_user(me, "pytest.apagar", "Segura123", "loja", store_id=maia[0])
    cid = conv.create_conversation("pytest.apagar", "q")
    users.delete_user(me, new["id"])
    with owner() as c:
        assert c.execute("SELECT count(*) FROM conversations WHERE id = %s", (cid,)).fetchone()[0] == 0


def test_options_follow_the_scope():
    opts = users.options(actor("gerente.maia"))
    assert opts["roles"] == ["loja"] and opts["brands"] == [] and len(opts["stores"]) == 1
    assert opts["defaults"]["loja"] == ["sql", "forecast", "orders"]


# ---------- conta admin ----------

def test_create_admin_from_environment(monkeypatch):
    monkeypatch.setenv("ADMIN_USERNAME", "pytest.admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "Painel#Seguro-2026")
    assert create_admin.main([]) == 0
    admin_user = authenticate("pytest.admin", "Painel#Seguro-2026")
    assert admin_user["role"] == "admin" and "observability" in admin_user["modules"]
    assert create_admin.main([]) == 0                            # repetir não muda nada


def test_create_admin_refuses_to_promote_a_demo_account(monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "Painel#Seguro-2026")
    assert create_admin.main(["pedro"]) == 1
    assert load_user("pedro")["role"] == "imperador"


def test_admin_queries_see_the_whole_group():
    _, rows = run_query("SELECT count(*) FROM stores", {"role": "admin", "brand_id": None, "store_id": None})
    _, everything = run_query("SELECT count(*) FROM stores", {"role": "imperador", "brand_id": None, "store_id": None})
    assert rows == everything and rows[0][0] > 1


# ---------- registo, avaliações e painel ----------

def make_trace(**kw) -> Trace:
    t = Trace()
    for k, v in kw.items():
        setattr(t, k, v)
    return t


def test_request_log_rating_and_metrics(maia):
    me = users.create_user(actor("gestor.burgerlab"), "pytest.metricas", "Segura123", "loja", store_id=maia[0])
    me = load_user(me["username"])
    ok = request_log.save_request(make_trace(intent="data", sql_attempts=1, llm_calls=2, prompt_tokens=900,
                                             completion_tokens=50), me, "Faturação de ontem?", "pt", "sql")
    bad = request_log.save_request(make_trace(sql_attempts=2, sql_failed=True, error="UndefinedColumn: x"),
                                   me, "pergunta impossível", "pt", "error")
    assert ok and bad
    assert request_log.rate(me, ok, 1) and request_log.rate(me, bad, -1)
    assert not request_log.rate(actor("pedro"), ok, -1)          # não é dele

    m = admin.metrics(1)
    s = m["summary"]
    assert s["requests"] >= 2 and s["errors"] >= 1 and s["thumbs_down"] >= 1
    assert 0 < s["error_rate"] <= 1 and s["p95_ms"] is not None
    assert m["daily"][-1]["requests"] >= 2 and len(m["daily"]) == 1
    assert any(r["question"] == "pergunta impossível" for r in m["thumbs_down"])
    assert any(r["question"] == "pergunta impossível" for r in m["recent_errors"])
    assert any(u["username"] == "pytest.metricas" for u in m["by_user"])
    assert m["eval_history"]


def test_rating_can_be_removed(maia):
    me = load_user(users.create_user(actor("gestor.burgerlab"), "pytest.rating", "Segura123", "loja",
                                     store_id=maia[0])["username"])
    rid = request_log.save_request(make_trace(), me, "q", "pt", "no_sql")
    request_log.rate(me, rid, 1)
    request_log.rate(me, rid, 0)
    with owner() as c:
        assert c.execute("SELECT rating, rated_at FROM request_log WHERE id = %s", (rid,)).fetchone() == (None, None)


def test_saving_the_log_never_breaks_the_answer():
    """Conta inexistente → FK falha → devolve None em vez de rebentar o /ask."""
    assert request_log.save_request(make_trace(), {"id": -1, "username": "pytest.x", "role": "loja"},
                                    "q", "pt", "sql") is None


# ---------- pool ----------

def test_readonly_pool_connections_cannot_write():
    with pool.connection("readonly") as conn:
        assert conn.read_only
        with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
            conn.execute("CREATE TEMP TABLE pytest_x (a int)")


def test_rls_context_does_not_leak_to_the_next_request():
    """O contexto é por transação: a ligação devolvida ao pool não leva o perfil."""
    run_query("SELECT 1", {"role": "loja", "brand_id": None, "store_id": 1})
    with pool.connection("readonly") as conn:
        assert conn.execute("SELECT current_setting('app.role', true)").fetchone()[0] in (None, "")


def test_pool_reuses_connections():
    """20 pedidos seguidos não abrem ligações novas: reutilizam as que já existem."""
    p = pool.get_pool("owner")
    with p.connection():
        pass
    opened = p.get_stats().get("connections_num", 0)
    pids = set()
    for _ in range(20):
        with pool.connection("owner") as conn:
            pids.add(conn.info.backend_pid)
    assert p.get_stats().get("connections_num", 0) == opened
    assert len(pids) <= pool.MAX_SIZE


# ---------- foto de perfil ----------

def test_avatar_roundtrip_and_db_constraint(maia):
    import base64

    from multistore_ai_assistant.api import profile
    me = load_user(users.create_user(actor("gestor.burgerlab"), "pytest.foto", "Segura123", "loja",
                                     store_id=maia[0])["username"])
    img = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20).decode()
    profile.set_avatar(me["username"], img)
    details = profile.me_details(me)
    assert details == {"avatar": img, "brand_name": "BurgerLab"}       # loja → marca da loja
    assert any(u["avatar"] == img for u in users.list_users(actor("gestor.burgerlab")))
    profile.set_avatar(me["username"], None)
    assert profile.me_details(me)["avatar"] is None
    with owner() as c, pytest.raises(psycopg.errors.CheckViolation):
        c.execute("UPDATE users SET avatar = 'data:text/html,<script>' WHERE username = 'pytest.foto'")


# ---------- definições ----------

def test_user_settings_persist_and_reset(maia):
    from multistore_ai_assistant.api import settings as st
    me = load_user(users.create_user(actor("gestor.burgerlab"), "pytest.defs", "Segura123", "loja",
                                     store_id=maia[0])["username"])
    assert st.get_user_settings(me) == {"lang": None, "theme": None, "accent": None}
    st.update_user_settings(me, {"theme": "dark", "accent": "orange"})
    assert st.update_user_settings(me, {"lang": "fr"}) == {"lang": "fr", "theme": "dark", "accent": "orange"}
    assert st.update_user_settings(me, {"accent": None})["accent"] is None
    assert st.update_user_settings(me, {"accent": "#C2185B"})["accent"] == "#c2185b"   # cor personalizada
    with owner() as c, pytest.raises(psycopg.errors.CheckViolation):
        c.execute("UPDATE user_settings SET accent = '#fff' WHERE user_id = %s", (me["id"],))


def test_app_settings_roundtrip_and_cache(monkeypatch):
    from multistore_ai_assistant.api import settings as st
    monkeypatch.setenv("ADMIN_USERNAME", "pytest.admin")
    monkeypatch.setenv("ADMIN_PASSWORD", "Painel#Seguro-2026")
    create_admin.main([])
    admin_user = load_user("pytest.admin")
    with owner() as c:
        before = c.execute("SELECT key, value FROM app_settings").fetchall()
    try:
        out = st.update_app_settings(admin_user, {"session_hours": 4, "show_demo_accounts": False,
                                                  "default_accent": "wine", "default_lang": "fr"})
        assert out["values"]["session_hours"] == 4 and out["updated_by"] == "pytest.admin"
        st.clear_cache()                                  # relê da BD (texto, número e booleano)
        assert st.public_config() == {"default_accent": "wine", "default_lang": "fr", "show_demo_accounts": False}
        assert "session_hours" not in st.public_config()
    finally:
        with owner() as c:
            c.execute("DELETE FROM app_settings")
            for key, value in before:
                c.execute("INSERT INTO app_settings (key, value) VALUES (%s, %s::jsonb)", (key, json.dumps(value)))
        st.clear_cache()


def test_llm_role_cannot_read_settings():
    for table in ("user_settings", "app_settings"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            run_query(f"SELECT * FROM {table}", {"role": "imperador", "brand_id": None, "store_id": None})
