"""Endpoints da API com a BD e o LLM simulados (FastAPI TestClient)."""
import pytest
from fastapi.testclient import TestClient

from multistore_ai_assistant.api import auth
from multistore_ai_assistant.api import main as api
from tests.conftest import IMPERADOR, LOJA, patch_route

client = TestClient(api.app)


def bearer(user=LOJA) -> dict:
    return {"Authorization": "Bearer " + auth.create_token(user)}


class Store:
    """Conversas guardadas em memória em vez da BD."""

    def __init__(self):
        self.convs = {}       # id -> (owner, title)
        self.messages = []    # (conv_id, role, content, sql, kind)
        self.results = []     # result (JSON) gravado com cada mensagem

    def exchange(self, c, question, answer, s=None, k=None, rid=None, res=None):
        """Pergunta + resposta gravadas juntas (como o ``add_exchange`` faz numa transação)."""
        self.messages += [(c, "user", question, None, None), (c, "assistant", answer, s, k)]
        self.results += [None, res]

    def install(self, mp):
        patch_route(mp, "owns", lambda u, c: self.convs.get(c, (None,))[0] == u)
        patch_route(mp, "create_conversation", self.create)
        patch_route(mp, "add_exchange", self.exchange)
        patch_route(mp, "get_history", lambda c: [("q anterior", "SELECT 1")])
        patch_route(mp, "list_conversations", lambda u: [
            {"id": i, "title": t} for i, (o, t) in self.convs.items() if o == u])
        patch_route(mp, "get_messages", lambda u, c: [] if self.convs.get(c, (None,))[0] == u else None)
        patch_route(mp, "rename_conversation", self.rename)
        patch_route(mp, "delete_conversation", lambda u, c: self.convs.get(c, (None,))[0] == u
                   and self.convs.pop(c) is not None)
        return self

    def create(self, user, question):
        cid = len(self.convs) + 1
        self.convs[cid] = (user, question[:60])
        return cid

    def rename(self, user, cid, title):
        if self.convs.get(cid, (None,))[0] != user:
            return False
        self.convs[cid] = (user, title)
        return True


@pytest.fixture
def store(monkeypatch):
    return Store().install(monkeypatch)


@pytest.fixture
def fake_ask(monkeypatch):
    calls = []

    def _ask(question, user, lang, history, on_event=None):
        calls.append((question, user, lang, history))
        return {"sql": "SELECT 1", "kind": "sql", "columns": ["x"], "rows": [[1]], "answer": "Um."}
    patch_route(monkeypatch, "ask", _ask)
    return calls


# ---------- página e headers ----------

def test_index_has_security_headers():
    r = client.get("/")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert r.headers["cache-control"] == "no-cache"          # nova versão da UI aparece logo


HTML = {"Accept": "text/html,application/xhtml+xml,*/*;q=0.8"}


@pytest.mark.parametrize("path", ["/login", "/chat", "/profile", "/users", "/admin", "/settings", "/review", "/chat/"])
def test_ui_pages_serve_the_app_to_the_browser(path):
    """URLs limpos: abrir /chat (ou recarregar) no browser devolve a UI, com os mesmos cabeçalhos."""
    r = client.get(path, headers=HTML)
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert '<div id="app"' in r.text
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["cache-control"] == "no-cache"


@pytest.mark.parametrize("path", ["/profile", "/users", "/review"])
def test_api_get_with_same_path_still_returns_json(path):
    """Os pedidos da UI levam token: /profile, /users e /review continuam a ser a API."""
    r = client.get(path, headers={**HTML, "Authorization": "Bearer x"})
    assert r.status_code == 401 and r.headers["content-type"].startswith("application/json")
    assert client.get(path).status_code == 401          # sem Accept: text/html também é a API


def test_unknown_client_path_still_gets_the_spa_shell():
    """Fallback SPA: caminhos sem ficheiro devolvem o index (o Vue Router decide)."""
    r = client.get("/nao-existe", headers=HTML)
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert 'id="app"' in r.text


@pytest.mark.parametrize("path", ["/chat", "/login", "/reset-password", "/dashboard"])
def test_vue_spa_serves_index_for_client_routes(path):
    """F5 em /chat (e afins) devolve o index.html do Vite, não 404."""
    r = client.get(path, headers=HTML)
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert 'id="app"' in r.text
    assert r.headers["cache-control"] == "no-cache"
    # CSP estrita da SPA: sem jsdelivr / unsafe-eval / scripts inline
    csp = r.headers["content-security-policy"]
    assert "jsdelivr" not in csp and "unsafe-eval" not in csp and "unsafe-inline" not in csp.split("script-src")[1].split(";")[0]


@pytest.mark.parametrize("path,dest", [
    ("/app", "/"),
    ("/app/", "/"),
    ("/app/chat", "/chat"),
    ("/app/login", "/login"),
    ("/app/reset-password", "/reset-password"),
    ("/app/assets/ok.js", "/assets/ok.js"),
])
def test_legacy_app_prefix_redirects(path, dest):
    r = client.get(path, headers=HTML, follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == dest


def test_legacy_app_redirect_keeps_the_query_string():
    r = client.get("/app/reset-password?token=abc&x=1", headers=HTML, follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/reset-password?token=abc&x=1"


def test_legacy_app_redirect_keeps_encoded_chars_in_the_path():
    """``%3F`` / ``%23`` / ``%25`` no caminho não passam a ser query, fragmento ou outro escape."""
    r = client.get("/app/a%3Fb%23c%25d?q=1", headers=HTML, follow_redirects=False)
    assert r.headers["location"] == "/a%3Fb%23c%25d?q=1"


@pytest.mark.parametrize("path,dest", [
    ("/app//evil.com", "/evil.com"),
    ("/app///evil.com/x", "/evil.com/x"),
    ("/app/\\evil.com", "/evil.com"),
    ("/app/\\/evil.com", "/evil.com"),
    ("/app//\\evil.com", "/evil.com"),
    ("/app/%2F%2Fevil.com", "/evil.com"),
    ("/app/%5Cevil.com", "/evil.com"),
])
def test_legacy_app_redirect_is_never_an_open_redirect(path, dest):
    """``/app//evil.com`` não pode dar ``Location: //evil.com`` (outro site para o browser)."""
    r = client.get(path, headers=HTML, follow_redirects=False)
    assert r.status_code == 307
    location = r.headers["location"]
    assert location == dest
    assert location.startswith("/") and location[1:2] not in ("/", "\\")


@pytest.mark.parametrize("path,dest", [
    ("/app", "/"), ("/app/", "/"), ("/app/chat", "/chat"), ("/app//evil.com", "/evil.com"),
    ("/app/\\evil.com", "/evil.com"), ("/app/\t/evil.com", "/evil.com"),
    ("/appointments", None), ("/chat", None), ("/", None),
])
def test_legacy_app_redirect_path(path, dest):
    assert api.legacy_app_redirect_path(path) == dest


def test_legacy_app_redirect_gets_security_headers():
    r = client.get("/app/chat", headers=HTML, follow_redirects=False)
    assert r.status_code == 307
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["cache-control"] == "no-store"


def test_legacy_app_redirect_lands_on_the_spa():
    r = client.get("/app/chat?x=1", headers=HTML)
    assert r.status_code == 200 and 'id="app"' in r.text
    assert str(r.url).endswith("/chat?x=1")


# ---------- fallback da SPA só para navegações ----------

def test_get_on_post_only_route_is_405_not_the_spa():
    r = client.get("/ask", headers=HTML)
    assert r.status_code == 405
    assert r.headers["content-type"].startswith("application/json")
    assert 'id="app"' not in r.text


@pytest.mark.parametrize("path", ["/api/nao-existe", "/ask/nao-existe", "/auth/x", "/health/x",
                                  "/conversations/1/nao-existe/x", "/docs/x", "/openapi.json"])
def test_unknown_api_path_is_json_404_not_the_spa(path):
    r = client.get(path, headers=HTML)
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")
    assert 'id="app"' not in r.text


@pytest.mark.parametrize("path", ["/admin/x", "/users/abc", "/settings/x/y", "/review/abc",
                                  "/profile/password", "/dashboard/x"])
def test_navigation_below_a_page_gets_the_spa(path):
    """/admin/x aberto no browser: o Vue Router decide (não um 404/405 JSON da API)."""
    r = client.get(path, headers=HTML)
    assert r.status_code == 200 and 'id="app"' in r.text
    assert r.headers["cache-control"] == "no-cache"


@pytest.mark.parametrize("headers", [{**HTML, "Authorization": "Bearer x"}, {"Accept": "application/json"}, {}])
def test_api_fetch_below_a_page_stays_json(headers):
    r = client.get("/admin/x", headers=headers)
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")


@pytest.mark.parametrize("path", ["/admin/metrics", "/users/options", "/settings/app"])
def test_real_api_route_below_a_page_stays_the_api(path):
    """Uma rota GET real continua a ser a API mesmo numa navegação (sem token: 401 JSON)."""
    r = client.get(path, headers=HTML)
    assert r.status_code == 401
    assert r.headers["content-type"].startswith("application/json")


def test_unknown_path_without_html_accept_is_404():
    """fetch/XHR (sem Accept: text/html) a um caminho desconhecido: 404, não o index.html."""
    r = client.get("/nao-existe", headers={"Accept": "application/json"})
    assert r.status_code == 404 and 'id="app"' not in r.text


def test_unknown_path_with_other_method_is_not_the_spa():
    r = client.post("/nao-existe", headers=HTML, json={})
    assert r.status_code in (404, 405) and 'id="app"' not in r.text
    assert r.headers["content-type"].startswith("application/json")


@pytest.mark.parametrize("path", ["/theme-boot.js", "/favicon.svg", "/site.webmanifest", "/assets/ok.js"])
def test_spa_static_files_are_served_without_html_accept(path):
    """Ficheiros reais do build saem sempre, seja qual for o Accept (scripts, ícones, manifest)."""
    r = client.get(path, headers={"Accept": "*/*"})
    assert r.status_code == 200


def test_api_prefixes_cover_the_api_routes():
    for prefix in ("/ask", "/conversations", "/health", "/admin", "/users", "/profile", "/api",
                   "/auth", "/docs", "/openapi.json"):
        assert prefix in api.API_PREFIXES
    assert not api.is_api_path("/nao-existe") and not api.is_api_path("/assets/ok.js")


# ---------- sem build do frontend ----------

@pytest.mark.parametrize("path", ["/", "/chat"])
def test_missing_frontend_build_is_a_clear_503(monkeypatch, tmp_path, path):
    from multistore_ai_assistant.api.routes import pages
    monkeypatch.setattr(pages, "APP_DIR", tmp_path / "dist")
    r = client.get(path, headers=HTML)
    assert r.status_code == 503
    assert r.json()["detail"]["message"] == "frontend not built, run npm run build in frontend"


def test_missing_frontend_build_favicon_is_404(monkeypatch, tmp_path):
    from multistore_ai_assistant.api.routes import pages
    monkeypatch.setattr(pages, "APP_DIR", tmp_path / "dist")
    assert client.get("/favicon.ico").status_code == 404


@pytest.mark.parametrize("path", ["/assets/missing.js", "/assets/foo", "/assets/",
                                  "/assets", "/assets/sub/x", "/assets/sub/"])
def test_vue_spa_unknown_asset_is_404_never_the_index(path):
    """Em /assets/ não há fallback: nunca o index.html (que ficaria em cache um ano)."""
    r = client.get(path, headers=HTML)
    assert r.status_code == 404
    assert 'id="app"' not in r.text
    assert r.headers["cache-control"] == "no-cache"


def test_vue_spa_asset_revalidation_keeps_the_long_cache():
    etag = client.get("/assets/ok.js").headers["etag"]
    r = client.get("/assets/ok.js", headers={"If-None-Match": etag})
    assert r.status_code == 304
    assert "immutable" in r.headers["cache-control"]


def test_vue_spa_existing_asset_is_immutable():
    r = client.get("/assets/ok.js")
    assert r.status_code == 200
    assert "immutable" in r.headers["cache-control"]
    assert "max-age=31536000" in r.headers["cache-control"]


def test_spa_csp_is_strict_everywhere():
    csp = client.get("/", headers=HTML).headers["content-security-policy"]
    assert "jsdelivr" not in csp and "unsafe-eval" not in csp
    assert "script-src 'self'" in csp


def test_api_and_health_are_not_spa_fallback():
    assert client.get("/health").json() == {"ok": True}
    # Pedido API com o mesmo prefixo de uma rota de página continua JSON 401
    r = client.get("/profile", headers={**HTML, "Authorization": "Bearer x"})
    assert r.status_code == 401 and r.headers["content-type"].startswith("application/json")


def test_api_responses_are_not_cached():
    assert client.get("/health").headers["cache-control"] == "no-store"


def test_health():
    assert client.get("/health").json() == {"ok": True}


@pytest.mark.parametrize("path", ["/docs", "/openapi.json", "/redoc"])
def test_docs_are_disabled_by_default(path):
    assert client.get(path).status_code == 404


# ---------- login ----------

def test_login_ok(monkeypatch):
    patch_route(monkeypatch, "authenticate", lambda u, p: {**LOJA} if p == "loja123" else None)
    r = client.post("/login", json={"username": "gerente.maia", "password": "loja123"})
    assert r.status_code == 200
    assert auth.current_user(auth.HTTPAuthorizationCredentials(scheme="Bearer", credentials=r.json()["token"]))["role"] == "loja"


def test_login_wrong_password(monkeypatch):
    patch_route(monkeypatch, "authenticate", lambda u, p: None)
    r = client.post("/login", json={"username": "x", "password": "y"})
    assert r.status_code == 401 and r.json()["detail"] == {"code": "bad_login",
                                                           "message": "Utilizador ou palavra-passe errados."}


@pytest.mark.parametrize("body", [
    {"username": "", "password": "x"},
    {"username": "a" * 65, "password": "x"},
    {"username": "a", "password": "x" * 129},
    {"username": "a"},
])
def test_login_validates_input(body):
    assert client.post("/login", json=body).status_code == 422


def test_login_brute_force_is_rate_limited(monkeypatch):
    patch_route(monkeypatch, "authenticate", lambda u, p: None)
    codes = [client.post("/login", json={"username": "pedro", "password": f"p{i}"}).status_code for i in range(12)]
    assert codes[:10] == [401] * 10 and codes[10:] == [429, 429]


# ---------- /ask ----------

@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer lixo"}, {"Authorization": "Basic abc"}])
def test_ask_requires_a_valid_token(headers):
    assert client.post("/ask", json={"question": "q"}, headers=headers).status_code in (401, 403)


def test_ask_creates_a_conversation_and_saves_both_messages(store, fake_ask):
    r = client.post("/ask", json={"question": "Lojas?", "lang": "en"}, headers=bearer())
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "Um." and body["conversation_id"] == 1
    assert store.convs[1][0] == "gerente.maia"
    assert [m[1] for m in store.messages] == ["user", "assistant"]
    question, user, lang, history = fake_ask[0]
    assert (question, user["role"], lang, history) == ("Lojas?", "loja", "en", [])


def test_ask_in_existing_conversation_sends_history(store, fake_ask):
    store.convs[7] = ("gerente.maia", "antiga")
    r = client.post("/ask", json={"question": "E no Porto?", "conversation_id": 7}, headers=bearer())
    assert r.status_code == 200 and r.json()["conversation_id"] == 7
    assert fake_ask[0][3] == [("q anterior", "SELECT 1")]


def test_cannot_ask_inside_someone_elses_conversation(store, fake_ask):
    store.convs[7] = ("pedro", "do imperador")
    r = client.post("/ask", json={"question": "q", "conversation_id": 7}, headers=bearer(LOJA))
    assert r.status_code == 404
    assert fake_ask == []                     # nem chegou a perguntar


def test_user_identity_comes_from_the_token_not_the_body(store, fake_ask):
    client.post("/ask", json={"question": "q", "role": "imperador", "store_id": None}, headers=bearer(LOJA))
    assert fake_ask[0][1]["role"] == "loja" and fake_ask[0][1]["store_id"] == 1


@pytest.mark.parametrize("body", [
    {"question": ""}, {"question": "a" * 501}, {"question": "q", "lang": "de"}, {"question": "q", "conversation_id": "x"},
])
def test_ask_validates_input(body):
    assert client.post("/ask", json=body, headers=bearer()).status_code == 422


@pytest.mark.parametrize("lang,word", [("pt", "indisponível"), ("en", "unavailable"),
                                       ("es", "disponible"), ("fr", "indisponible")])
def test_ask_hides_internal_errors(monkeypatch, store, lang, word):
    def boom(*a, **k):
        raise RuntimeError("password=supersecret em psycopg")
    patch_route(monkeypatch, "ask", boom)
    r = client.post("/ask", json={"question": "q", "lang": lang}, headers=bearer())
    assert r.status_code == 503
    assert word in r.json()["detail"]["message"] and "supersecret" not in r.text


def test_ask_is_rate_limited_per_user(store, fake_ask):
    codes = [client.post("/ask", json={"question": "q"}, headers=bearer(LOJA)).status_code for _ in range(21)]
    assert codes[:20] == [200] * 20 and codes[20] == 429
    # outro utilizador não é afetado
    assert client.post("/ask", json={"question": "q"}, headers=bearer(IMPERADOR)).status_code == 200


# ---------- conversas ----------

def test_list_only_my_conversations(store):
    store.convs.update({1: ("gerente.maia", "minha"), 2: ("pedro", "do pedro")})
    r = client.get("/conversations", headers=bearer(LOJA))
    assert r.json() == [{"id": 1, "title": "minha"}]


@pytest.mark.parametrize("method,path,body", [
    ("get", "/conversations/2", None),
    ("patch", "/conversations/2", {"title": "roubada"}),
    ("delete", "/conversations/2", None),
])
def test_other_users_conversations_are_404(store, method, path, body):
    store.convs[2] = ("pedro", "do pedro")
    kwargs = {"headers": bearer(LOJA)} | ({"json": body} if body else {})
    assert getattr(client, method)(path, **kwargs).status_code == 404
    assert store.convs[2] == ("pedro", "do pedro")


def test_rename_and_delete_my_conversation(store):
    store.convs[3] = ("gerente.maia", "velho")
    assert client.patch("/conversations/3", json={"title": " novo "}, headers=bearer()).status_code == 200
    assert client.delete("/conversations/3", headers=bearer()).status_code == 200
    assert 3 not in store.convs


@pytest.mark.parametrize("title", ["", "a" * 81])
def test_rename_validates_title(store, title):
    store.convs[3] = ("gerente.maia", "velho")
    assert client.patch("/conversations/3", json={"title": title}, headers=bearer()).status_code == 422


def test_blank_title_is_rejected(store):
    store.convs[3] = ("gerente.maia", "velho")
    assert client.patch("/conversations/3", json={"title": "   "}, headers=bearer()).status_code == 404
    assert store.convs[3][1] == "velho"


def test_conversations_are_rate_limited(store):
    codes = [client.get("/conversations", headers=bearer()).status_code for _ in range(61)]
    assert codes[-1] == 429 and set(codes[:60]) == {200}


# ---------- feedback (RAG) ----------

@pytest.fixture
def saved(monkeypatch):
    calls = []
    patch_route(monkeypatch, "add_example", lambda q, s, source, created_by=None: calls.append((q, s, source)))
    patch_route(monkeypatch, "run_query", lambda sql, user: (["QUERY PLAN"], [("Seq Scan",)]))
    return calls


def test_feedback_rejects_sql_that_does_not_run(saved, monkeypatch):
    """Válido para o sqlglot mas com uma coluna que não existe: não entra no RAG."""
    import psycopg

    def boom(sql, user):
        assert sql.startswith("EXPLAIN ")
        raise psycopg.errors.UndefinedColumn('column "x" does not exist')
    patch_route(monkeypatch, "run_query", boom)
    r = client.post("/feedback", json={"question": "q", "sql": "SELECT x FROM sales"}, headers=bearer(IMPERADOR))
    assert r.status_code == 400 and saved == []


def test_feedback_only_for_imperador(saved):
    r = client.post("/feedback", json={"question": "q", "sql": "SELECT 1"}, headers=bearer(LOJA))
    assert r.status_code == 403 and saved == []


def test_feedback_validates_sql(saved):
    r = client.post("/feedback", json={"question": "q", "sql": "DELETE FROM sales"}, headers=bearer(IMPERADOR))
    assert r.status_code == 400 and saved == []


def test_feedback_saves_normalised_sql(saved):
    r = client.post("/feedback", json={"question": "Lojas?", "sql": "select name from stores;"}, headers=bearer(IMPERADOR))
    assert r.status_code == 200
    assert saved == [("Lojas?", "SELECT name FROM stores", "feedback")]
