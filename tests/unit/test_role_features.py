"""Funcionalidades por perfil: rotas (403) e o router de intenção (recusa traduzida)."""
import json

import pytest
from fastapi.testclient import TestClient

from multistore_ai_assistant.api import features as role_features
from multistore_ai_assistant.api import main as api
from multistore_ai_assistant.api.auth import create_token
from multistore_ai_assistant.assistant import ask as ask_mod
from multistore_ai_assistant.assistant.ask import FEATURE_DENIED, ask
from tests.conftest import ADMIN, IMPERADOR, LOJA, MARCA, patch_route

client = TestClient(api.app)
ROLES = (ADMIN, IMPERADOR, MARCA, LOJA)


def bearer(user) -> dict:
    return {"Authorization": "Bearer " + create_token(user)}


def allow(username: str, *features: str, fake_users) -> None:
    fake_users[username]["features"] = list(features)


@pytest.fixture
def quiet_ask(monkeypatch):
    def _ask(question, user, lang, history, on_event=None):
        return {"sql": "SELECT 1", "kind": "sql", "answer": "ok", "columns": ["x"], "rows": [[1]]}
    patch_route(monkeypatch, "ask", _ask)


@pytest.fixture
def quiet_side(monkeypatch):
    patch_route(monkeypatch, "list_conversations", lambda u: [])
    monkeypatch.setattr(
        "multistore_ai_assistant.api.routes.review.review_db.pending", lambda: {"pending": 0})
    monkeypatch.setattr(
        "multistore_ai_assistant.api.routes.examples.rag_examples.list_examples", lambda: [])
    monkeypatch.setattr(
        "multistore_ai_assistant.api.routes.dashboard.dashboard_for", lambda user: {"revenue": {}})
    monkeypatch.setattr(
        "multistore_ai_assistant.api.routes.admin.admin_metrics.metrics", lambda days: {"days": days})
    monkeypatch.setattr(
        "multistore_ai_assistant.api.routes.settings.settings_db.app_settings_details",
        lambda: {"values": {}})
    monkeypatch.setattr(
        "multistore_ai_assistant.api.routes.users.users_db.list_users", lambda user: [])
    monkeypatch.setattr(role_features, "_write", lambda role, features: None)


# ---------- rotas: permitido e recusado por perfil ----------

ROUTE_CASES = [
    ("dashboard", "get", "/dashboard", ()),
    ("review", "get", "/review", ()),
    ("review", "get", "/examples", ()),
    ("users", "get", "/users", ()),
    ("admin", "get", "/admin/metrics", ()),
]


@pytest.mark.parametrize("feature,method,path,body", ROUTE_CASES)
@pytest.mark.parametrize("user", ROLES)
def test_route_follows_the_role_feature(quiet_side, fake_users, feature, method, path, body, user):
    """Com a funcionalidade (e o módulo que a rota já exigia) passa; sem ela, 403."""
    modules = ["sql", "forecast", "orders", "teach", "users", "observability"]
    fake_users[user["username"]]["modules"] = modules
    call = getattr(client, method)
    allow(user["username"], feature, fake_users=fake_users)
    allowed = call(path, headers=bearer(user))
    assert allowed.status_code != 403, allowed.text

    allow(user["username"], *(f for f in role_features.FEATURES if f != feature), fake_users=fake_users)
    denied = call(path, headers=bearer(user))
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "no_feature"


def test_ask_without_chat_forecast_or_orders_is_403(quiet_ask, fake_users):
    allow("gerente.maia", "dashboard", fake_users=fake_users)
    r = client.post("/ask", json={"question": "Lojas?"}, headers=bearer(LOJA))
    assert r.status_code == 403 and r.json()["detail"]["code"] == "no_feature"


def test_ask_is_allowed_with_only_forecast(quiet_ask, fake_users):
    allow("gerente.maia", "forecast", fake_users=fake_users)
    r = client.post("/ask", json={"question": "Quanto vou vender?"}, headers=bearer(LOJA))
    assert r.status_code == 200


def test_explain_needs_the_chat_feature(monkeypatch, fake_users):
    patch_route(monkeypatch, "sql_of_request", lambda u, rid: "SELECT 1")
    patch_route(monkeypatch, "explain_sql", lambda sql, lang: "porque")
    allow("pedro", "forecast", fake_users=fake_users)
    r = client.post("/explain", json={"request_id": 1, "lang": "pt"}, headers=bearer(IMPERADOR))
    assert r.status_code == 403 and r.json()["detail"]["code"] == "no_feature"
    allow("pedro", "chat", fake_users=fake_users)
    assert client.post("/explain", json={"request_id": 1, "lang": "pt"},
                       headers=bearer(IMPERADOR)).status_code == 200


def test_feedback_needs_the_review_feature(monkeypatch, fake_users):
    patch_route(monkeypatch, "teachable_sql", lambda sql, user: sql)
    patch_route(monkeypatch, "add_example", lambda *a, **k: 1)
    allow("pedro", "chat", fake_users=fake_users)
    r = client.post("/feedback", json={"question": "q", "sql": "SELECT 1"}, headers=bearer(IMPERADOR))
    assert r.status_code == 403 and r.json()["detail"]["code"] == "no_feature"


def test_alerts_need_chat_or_orders(monkeypatch, fake_users):
    patch_route(monkeypatch, "alerts_for", lambda user, lang: [])
    allow("gerente.maia", "dashboard", fake_users=fake_users)
    assert client.get("/alerts", headers=bearer(LOJA)).status_code == 403
    allow("gerente.maia", "orders", fake_users=fake_users)
    assert client.get("/alerts", headers=bearer(LOJA)).status_code == 200


def test_admin_edits_role_features_and_they_apply(quiet_side, fake_users):
    r = client.put("/admin/features", json={"role": "loja", "features": ["chat"]},
                   headers=bearer(ADMIN))
    assert r.status_code == 200 and r.json()["features"] == ["chat"]
    assert client.get("/dashboard", headers=bearer(LOJA)).status_code == 403
    assert client.get("/conversations", headers=bearer(LOJA)).status_code == 200
    listed = client.get("/admin/features", headers=bearer(ADMIN)).json()
    assert listed["roles"]["loja"] == ["chat"]
    assert "admin" in listed["roles"]["admin"]


def test_admin_cannot_drop_its_own_admin_feature():
    r = client.put("/admin/features", json={"role": "admin", "features": ["chat"]},
                   headers=bearer(ADMIN))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "admin_feature_locked"


def test_unknown_feature_is_rejected():
    r = client.put("/admin/features", json={"role": "loja", "features": ["root"]},
                   headers=bearer(ADMIN))
    assert r.status_code == 422


def test_app_settings_need_the_admin_feature(quiet_side, fake_users):
    allow("dono", "chat", fake_users=fake_users)
    denied = client.get("/settings/app", headers=bearer(ADMIN))
    assert denied.status_code == 403 and denied.json()["detail"]["code"] == "no_feature"
    allow("dono", "admin", fake_users=fake_users)
    assert client.get("/settings/app", headers=bearer(ADMIN)).status_code == 200


def test_imperador_cannot_edit_features_even_with_the_flag(quiet_side, fake_users):
    """Mesmo com a funcionalidade admin na lista, só o perfil admin vê e edita as permissões."""
    allow("pedro", *role_features.FEATURES, fake_users=fake_users)
    fake_users["pedro"]["modules"] = ["sql", "observability"]
    r = client.get("/admin/features", headers=bearer(IMPERADOR))
    assert r.status_code == 403 and r.json()["detail"]["code"] == "admin_only"
    r = client.put("/admin/features", json={"role": "imperador", "features": ["chat", "admin"]},
                   headers=bearer(IMPERADOR))
    assert r.status_code == 403 and r.json()["detail"]["code"] == "admin_only"
    assert "admin" not in role_features.features_for("imperador")


def test_admin_without_the_admin_feature_cannot_edit_features(quiet_side, fake_users):
    allow("dono", "chat", fake_users=fake_users)
    r = client.get("/admin/features", headers=bearer(ADMIN))
    assert r.status_code == 403 and r.json()["detail"]["code"] == "no_feature"


@pytest.mark.parametrize("role", ["imperador", "marca", "loja"])
def test_admin_feature_cannot_be_granted_to_another_role(quiet_side, role):
    r = client.put("/admin/features", json={"role": role, "features": ["chat", "admin"]},
                   headers=bearer(ADMIN))
    assert r.status_code == 400 and r.json()["detail"]["code"] == "admin_feature_admin_only"
    assert "admin" not in role_features.features_for(role)


def test_admin_features_lists_users_for_every_role(quiet_side):
    roles = client.get("/admin/features", headers=bearer(ADMIN)).json()["roles"]
    assert all("users" in feats for feats in roles.values())
    assert [r for r, feats in roles.items() if "admin" in feats] == ["admin"]


# ---------- chat e conversas: chat, previsão OU encomendas ----------

@pytest.mark.parametrize("feature", ["chat", "forecast", "orders"])
def test_conversations_open_with_any_chat_feature(quiet_side, monkeypatch, fake_users, feature):
    patch_route(monkeypatch, "get_messages", lambda u, c: [])
    allow("gerente.maia", feature, fake_users=fake_users)
    assert client.get("/conversations", headers=bearer(LOJA)).status_code == 200
    assert client.get("/conversations/7", headers=bearer(LOJA)).status_code == 200


def test_conversations_and_pdf_need_a_chat_feature(quiet_side, monkeypatch, fake_users):
    patch_route(monkeypatch, "get_messages", lambda u, c: [])
    allow("gerente.maia", "dashboard", "users", fake_users=fake_users)
    for path in ("/conversations", "/conversations/7", "/conversations/7/pdf"):
        r = client.get(path, headers=bearer(LOJA))
        assert r.status_code == 403 and r.json()["detail"]["code"] == "no_feature", path


def test_pdf_export_with_only_forecast(monkeypatch, fake_users):
    patch_route(monkeypatch, "conversation_title", lambda u, c: None)
    allow("gerente.maia", "forecast", fake_users=fake_users)
    r = client.get("/conversations/7/pdf", headers=bearer(LOJA))
    assert r.status_code == 404          # passou a verificação; a conversa é que não existe


# ---------- contas: módulo users + funcionalidade users ----------

def test_users_need_the_users_feature(quiet_side, fake_users):
    assert client.get("/users", headers=bearer(MARCA)).status_code == 200      # predefinição
    allow("gestor.burgerlab", "chat", fake_users=fake_users)
    r = client.get("/users", headers=bearer(MARCA))
    assert r.status_code == 403 and r.json()["detail"]["code"] == "no_feature"


def test_users_still_need_the_users_module(quiet_side, fake_users):
    fake_users["gestor.burgerlab"]["modules"] = ["sql"]
    r = client.get("/users", headers=bearer(MARCA))
    assert r.status_code == 403 and r.json()["detail"]["code"] == "no_module"


# ---------- cache de SQL: não devolve linhas sem chat ----------

CACHED_SQL = "SELECT 1"


@pytest.fixture
def cached_answer(monkeypatch):
    """O ``ask`` real com uma pergunta de dados já em cache (BD e LLM simulados)."""
    calls = {"lookup": 0, "query": 0, "generate": 0}

    def lookup(question, user):
        calls["lookup"] += 1
        return {"sql": CACHED_SQL, "question": question, "distance": 0.0}

    def run(sql, user):
        calls["query"] += 1
        return ["faturacao"], [[1234]]

    def generate(*a, **k):
        calls["generate"] += 1
        return CACHED_SQL

    monkeypatch.setattr(ask_mod, "classify", lambda q: ("data", 0.99))
    monkeypatch.setattr(ask_mod, "cache_lookup", lookup)
    monkeypatch.setattr(ask_mod, "run_query", run)
    monkeypatch.setattr(ask_mod, "generate_sql", generate)
    monkeypatch.setattr(ask_mod, "validate_sql", lambda sql: sql)
    monkeypatch.setattr(ask_mod, "answer", lambda *a, **k: "Faturação: 1234")
    monkeypatch.setattr(ask_mod, "cache_store", lambda *a, **k: None)
    monkeypatch.setattr(ask_mod, "record_cache_hit", lambda: None)
    patch_route(monkeypatch, "create_conversation", lambda u, q: 99)
    patch_route(monkeypatch, "add_exchange", lambda *a, **k: None)
    return calls


def sse_done(response) -> dict:
    events = [json.loads(c[len("data: "):]) for c in response.text.split("\n\n") if c.startswith("data: ")]
    assert events[-1]["type"] == "done", events
    assert not [e for e in events if e["type"] == "data"]
    return events[-1]


def test_cached_question_is_refused_without_chat_on_ask(cached_answer, fake_users):
    allow("gerente.maia", "forecast", fake_users=fake_users)
    r = client.post("/ask", json={"question": "Faturação de ontem", "lang": "en"}, headers=bearer(LOJA))
    body = r.json()
    assert r.status_code == 200 and body["kind"] == "denied"
    assert body["answer"] == FEATURE_DENIED["chat"]["en"]
    assert "rows" not in body and "1234" not in r.text
    assert cached_answer == {"lookup": 0, "query": 0, "generate": 0}


def test_cached_question_is_refused_without_chat_on_stream(cached_answer, fake_users):
    allow("gerente.maia", "orders", fake_users=fake_users)
    r = client.post("/ask/stream", json={"question": "Faturação de ontem", "lang": "fr"},
                    headers=bearer(LOJA))
    done = sse_done(r)
    assert done["kind"] == "denied" and done["answer"] == FEATURE_DENIED["chat"]["fr"]
    assert "1234" not in r.text
    assert cached_answer == {"lookup": 0, "query": 0, "generate": 0}


def test_cached_question_is_answered_with_chat(cached_answer, fake_users):
    allow("gerente.maia", "chat", fake_users=fake_users)
    r = client.post("/ask", json={"question": "Faturação de ontem"}, headers=bearer(LOJA))
    body = r.json()
    assert body["kind"] == "sql" and body["cached"] is True and body["rows"] == [[1234]]
    assert cached_answer["lookup"] == 1 and cached_answer["generate"] == 0


def test_cached_question_is_answered_with_chat_on_stream(cached_answer, fake_users):
    allow("gerente.maia", "chat", fake_users=fake_users)
    r = client.post("/ask/stream", json={"question": "Faturação de ontem"}, headers=bearer(LOJA))
    events = [json.loads(c[len("data: "):]) for c in r.text.split("\n\n") if c.startswith("data: ")]
    assert events[-1]["type"] == "done" and events[-1]["rows"] == [[1234]]


def test_unsure_question_without_chat_never_reaches_the_cache_or_the_database(cached_answer, monkeypatch):
    """Classificador incerto: o LLM ainda etiqueta, mas SQL sem chat é recusado sem correr."""
    monkeypatch.setattr(ask_mod, "classify", lambda q: (None, 0.2))
    result = ask("Faturação de ontem", {**LOJA, "features": ["forecast"]}, "pt")
    assert result["kind"] == "denied" and result["sql"] is None and "rows" not in result
    assert cached_answer == {"lookup": 0, "query": 0, "generate": 1}


def test_unsure_forecast_question_still_works_for_a_forecast_only_role(monkeypatch):
    monkeypatch.setattr(ask_mod, "classify", lambda q: (None, 0.2))
    monkeypatch.setattr(ask_mod, "generate_sql", lambda *a, **k: "FORECAST")
    monkeypatch.setattr(ask_mod, "forecast_answer", lambda u: (["day"], [("d", 1)]))
    monkeypatch.setattr(ask_mod, "answer", lambda *a, **k: "número")
    result = ask("E para a semana?", {**LOJA, "features": ["forecast"]}, "pt")
    assert result["kind"] == "forecast" and result["rows"]


def test_confident_data_question_without_chat_does_not_call_the_llm(cached_answer):
    result = ask("Faturação de ontem", {**LOJA, "features": ["forecast", "orders"]}, "es")
    assert result["answer"] == FEATURE_DENIED["chat"]["es"]
    assert cached_answer["generate"] == 0


def test_no_chat_forecast_or_orders_does_not_call_the_llm_even_if_unsure(cached_answer, monkeypatch):
    monkeypatch.setattr(ask_mod, "classify", lambda q: (None, 0.2))
    result = ask("Faturação de ontem", {**LOJA, "features": ["dashboard"]}, "pt")
    assert result["kind"] == "denied" and cached_answer["generate"] == 0


# ---------- cópia em memória: releitura e tabela vazia ----------

class FakeConn:
    def __init__(self, rows):
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, *a):
        return self

    def fetchall(self):
        return self.rows


def use_db(monkeypatch, rows):
    from multistore_ai_assistant.db import pool
    reads = []

    def connection(kind="owner"):
        reads.append(kind)
        return FakeConn(rows)
    monkeypatch.setattr(pool, "connection", connection)
    monkeypatch.setenv("ROLE_FEATURES_FROM_DB", "1")
    return reads


def test_empty_role_features_falls_back_to_the_defaults(monkeypatch, caplog):
    use_db(monkeypatch, [])
    role_features._table["loja"] = set()
    with caplog.at_level("WARNING", logger="multistore"):
        role_features.load_from_db()
    assert role_features.features_for("loja") == [
        f for f in role_features.FEATURES if f in role_features.DEFAULT_ROLE_FEATURES["loja"]]
    assert "vazia" in caplog.text


def test_role_features_are_reread_after_the_ttl(monkeypatch):
    reads = use_db(monkeypatch, [("admin", "admin"), ("loja", "chat")])
    role_features.load_from_db()
    assert role_features.features_for("loja") == ["chat"] and len(reads) == 1

    use_db_rows = [("admin", "admin"), ("loja", "chat"), ("loja", "dashboard")]
    reads = use_db(monkeypatch, use_db_rows)
    assert not role_features.has_feature({"role": "loja"}, "dashboard")       # dentro do TTL
    assert reads == []
    monkeypatch.setattr(role_features, "_loaded_at", role_features._loaded_at - role_features.REFRESH_SECONDS)
    assert role_features.has_feature({"role": "loja"}, "dashboard")           # releu
    assert len(reads) == 1


def test_a_failed_reread_keeps_the_current_copy(monkeypatch):
    from multistore_ai_assistant.db import pool

    def broken(kind="owner"):
        raise RuntimeError("bd em baixo")
    monkeypatch.setattr(pool, "connection", broken)
    monkeypatch.setenv("ROLE_FEATURES_FROM_DB", "1")
    assert role_features.has_feature({"role": "loja"}, "chat")


def test_reload_swaps_the_table_without_an_empty_gap(monkeypatch):
    """A nova tabela entra num só passo: durante a leitura da BD a anterior continua visível."""
    previous = role_features._table
    assert previous.get("loja")
    seen = []

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

        def execute(self, *a):
            seen.append(role_features._table)
            return self

        def fetchall(self):
            seen.append(role_features._table)
            return [("admin", "admin"), ("loja", "chat")]

    from multistore_ai_assistant.db import pool
    monkeypatch.setattr(pool, "connection", lambda kind="owner": Conn())
    monkeypatch.setenv("ROLE_FEATURES_FROM_DB", "1")
    role_features.load_from_db()
    assert seen and all(snap is previous and snap.get("loja") for snap in seen)
    assert role_features._table is not previous
    assert role_features.features_for("loja") == ["chat"]


def test_db_rows_granting_admin_to_another_role_are_ignored(monkeypatch):
    use_db(monkeypatch, [("admin", "chat"), ("loja", "admin"), ("loja", "chat")])
    role_features.load_from_db()
    assert role_features.features_for("loja") == ["chat"]
    assert "admin" in role_features.features_for("admin")


def test_put_updates_this_process_immediately(quiet_side, monkeypatch):
    use_db(monkeypatch, [("admin", "admin")])
    monkeypatch.setattr(role_features, "_loaded_at", 10**12)          # releitura muito longe
    r = client.put("/admin/features", json={"role": "marca", "features": ["chat"]}, headers=bearer(ADMIN))
    assert r.status_code == 200
    assert role_features.features_for("marca") == ["chat"]


# ---------- intenção: recusa traduzida, sem dados ----------

QUESTIONS = {
    "forecast": "Quanto vou vender na próxima semana?",
    "orders": "Que ingredientes devo encomendar?",
}


@pytest.mark.parametrize("intent", ["forecast", "orders"])
@pytest.mark.parametrize("lang", ["pt", "en", "es", "fr"])
def test_intent_without_the_feature_is_a_translated_refusal(monkeypatch, intent, lang):
    monkeypatch.setattr(ask_mod, "classify", lambda q: (intent, 0.99))
    monkeypatch.setattr(ask_mod, "forecast_answer", lambda u: (_ for _ in ()).throw(AssertionError("model")))
    monkeypatch.setattr(ask_mod, "orders_answer", lambda u: (_ for _ in ()).throw(AssertionError("model")))
    user = {**LOJA, "features": ["chat"]}
    result = ask(QUESTIONS[intent], user, lang)
    assert result["kind"] == "denied" and result["feature"] == intent
    assert result["answer"] == FEATURE_DENIED[intent][lang]
    assert "rows" not in result and result["sql"] is None


@pytest.mark.parametrize("intent", ["forecast", "orders"])
def test_intent_with_the_feature_still_returns_the_model(monkeypatch, intent):
    monkeypatch.setattr(ask_mod, "classify", lambda q: (intent, 0.99))
    monkeypatch.setattr(ask_mod, "forecast_answer", lambda u: (["day"], [("d", 1)]))
    monkeypatch.setattr(ask_mod, "orders_answer", lambda u: (["ingredient"], [("Pão", 2)]))
    monkeypatch.setattr(ask_mod, "answer", lambda *a, **k: "número")
    result = ask(QUESTIONS[intent], {**LOJA, "features": [intent]}, "pt")
    assert result["kind"] == intent and result["rows"]


def test_sql_from_the_llm_without_chat_is_refused(monkeypatch):
    monkeypatch.setattr(ask_mod, "classify", lambda q: (None, 0.1))
    monkeypatch.setattr(ask_mod, "generate_sql", lambda *a, **k: "SELECT 1")
    monkeypatch.setattr(ask_mod, "run_query", lambda *a, **k: (_ for _ in ()).throw(AssertionError("ran")))
    result = ask("Faturação?", {**MARCA, "features": ["forecast"]}, "en")
    assert result["answer"] == FEATURE_DENIED["chat"]["en"]
    assert result["sql"] is None


def test_llm_label_forecast_is_refused_without_the_feature(monkeypatch):
    monkeypatch.setattr(ask_mod, "classify", lambda q: (None, 0.1))
    monkeypatch.setattr(ask_mod, "generate_sql", lambda *a, **k: "FORECAST")
    monkeypatch.setattr(ask_mod, "forecast_answer", lambda u: (_ for _ in ()).throw(AssertionError("model")))
    result = ask("q", {**LOJA, "features": ["chat"]}, "es")
    assert result["answer"] == FEATURE_DENIED["forecast"]["es"]
