"""Aplicação FastAPI: monta os routers, os cabeçalhos de segurança e o formato dos erros.

As rotas estão em ``api/routes/`` (uma por área); as dependências partilhadas
(limites de pedidos, acesso por módulo) em ``api/deps.py``; os corpos dos
pedidos em ``api/schemas.py``. A lógica de negócio fica em ``assistant/``.
"""
import logging
import mimetypes
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.routing import Match, Mount
from starlette.types import Scope

from multistore_ai_assistant.api.errors import CATALOG, ApiError, request_lang, tr
from multistore_ai_assistant.api.routes import (
    admin,
    ask,
    auth,
    avatars,
    conversations,
    dashboard,
    examples,
    pages,
    password,
    profile,
    review,
    settings,
    users,
)
from multistore_ai_assistant.api.routes.pages import APP_DIR, UI_PATHS, index_page, is_page_request
from multistore_ai_assistant.db.pool import close_pools
from multistore_ai_assistant.intent.predict import backend as intent_backend

mimetypes.add_type("application/manifest+json", ".webmanifest")   # o Windows não o conhece
mimetypes.add_type("image/svg+xml", ".svg")

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("multistore")

# SPA Vue (Vite) em frontend/dist — servida em /. VUE_APP_DIR (em pages) aponta nos
# testes para tests/fixtures/vue_dist. /app e /app/… redirecionam para / e /… (links antigos).

INTENT_NAMES = {
    "xlmr": "XLM-RoBERTa (models/intent-xlmr)",
    "minilm": "MiniLM + LogReg (models/intent.joblib)",
    "none": "nenhum, decide sempre o LLM",
}


def legacy_app_redirect_path(path: str) -> str | None:
    """``/app`` → ``/``, ``/app/chat`` → ``/chat``; ``None`` se não for o prefixo antigo.

    O destino começa sempre por uma única ``/``: ``/app//evil.com`` ou ``/app/\\evil.com``
    dariam ``//evil.com`` (outro site para o browser), por isso as barras (``/`` e ``\\``) e
    espaços/controlo no início do resto são removidos.
    """
    if path != "/app" and not path.startswith("/app/"):
        return None
    return "/" + path[len("/app"):].lstrip("/\\ \t\r\n\x0b\x0c")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Arranque: regista o classificador ativo. Fim: fecha os pools de ligações."""
    log.info("Classificador de intenção: %s", INTENT_NAMES[intent_backend()])
    try:
        from multistore_ai_assistant.api.features import load_from_db
        load_from_db()
    except Exception:
        log.warning("Funcionalidades por perfil: a usar as predefinições", exc_info=True)
    yield
    close_pools()


# /docs só fica ativo se ENABLE_DOCS=1 (útil em desenvolvimento)
DOCS = os.getenv("ENABLE_DOCS") == "1"
app = FastAPI(
    title="Multistore AI Assistant",
    docs_url="/docs" if DOCS else None,
    redoc_url=None,
    openapi_url="/openapi.json" if DOCS else None,
    lifespan=lifespan,
)


@app.exception_handler(ApiError)
def api_error(request: Request, exc: ApiError):
    """Todos os erros no mesmo formato: ``{"detail": {"code", "message"}}`` na língua do pedido."""
    lang = getattr(exc, "lang", None) or request_lang(request)
    message = tr(exc.code, lang, **exc.params) if exc.code in CATALOG else exc.message
    return JSONResponse(status_code=exc.status, content={"detail": {"code": exc.code, "message": message}},
                        headers=getattr(exc, "headers", None))


# SPA Vite: só scripts do próprio origin (theme-boot.js + bundles)
CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)


@app.middleware("http")
async def ui_pages(request: Request, call_next):
    """``/chat``, ``/login``, … abertos no browser devolvem a UI (o router Vue escolhe a página).

    Fica por dentro de ``security_headers``, por isso a página também leva os cabeçalhos.
    """
    if is_page_request(request):
        return index_page()
    return await call_next(request)


# Registado entre ui_pages e security_headers: corre antes das páginas, mas o 307 também leva
# os cabeçalhos de segurança e o Cache-Control (o último middleware registado é o de fora).
@app.middleware("http")
async def redirect_legacy_app_prefix(request: Request, call_next):
    """Links antigos ``/app/…`` passam a ``/…`` (mantém a query string)."""
    # scope["path"] (já descodificado): request.url.path troca ``\`` por ``%5C`` e escaparia
    # à limpeza. ``?`` e ``#`` do caminho voltam a ser escapados para não mudarem o URL.
    dest = legacy_app_redirect_path(request.scope["path"])
    if dest is not None:
        dest = dest.replace("%", "%25").replace("?", "%3F").replace("#", "%23")
        if request.url.query:
            dest = f"{dest}?{request.url.query}"
        return RedirectResponse(url=dest, status_code=307)
    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Aplica cabeçalhos de segurança a todas as respostas HTTP."""
    response = await call_next(request)
    path = request.url.path
    response.headers["Content-Security-Policy"] = CSP
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    # API: never store. /assets/*: só os ficheiros reais (200, ou 304 a revalidar um deles)
    # são immutable; lá não há fallback para o index.html, e um 404 fica no-cache.
    if "cache-control" not in response.headers:
        ct = response.headers.get("content-type", "")
        under_assets = path == "/assets" or path.startswith("/assets/")
        if under_assets and response.status_code in (200, 304):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif (under_assets
              or "text/html" in ct
              or path in ("/", "/favicon.ico", "/favicon.svg", "/theme-boot.js", "/site.webmanifest")
              or path.startswith("/icons/") or path.startswith("/img/")
              or is_page_request(request)):
            response.headers["Cache-Control"] = "no-cache"
        else:
            response.headers["Cache-Control"] = "no-store"
    return response


API_MODULES = (auth, password, profile, avatars, ask, conversations, dashboard,
               users, admin, review, examples, settings, pages)
for module in API_MODULES:
    app.include_router(module.router)

# Sem /docs: estes caminhos não podem cair no fallback da SPA (senão devolvem index.html).
if not DOCS:
    def _docs_disabled():
        raise HTTPException(status_code=404)

    for _path in ("/docs", "/redoc", "/openapi.json"):
        app.add_api_route(_path, _docs_disabled, methods=["GET", "HEAD"], include_in_schema=False)

# Primeiro segmento de cada rota da API (/ask, /conversations, /health, …) e alguns reservados.
# Estes caminhos nunca vão para a SPA: um GET desconhecido dá o 404 JSON, e um GET a uma rota
# só POST (ex. /ask) volta a dar 405.
# (Lê os routers de cada módulo: no FastAPI recente app.routes guarda-os embrulhados.)
API_PREFIXES = frozenset(
    {"/" + r.path.strip("/").split("/", 1)[0] for module in API_MODULES for r in module.router.routes
     if isinstance(r, APIRoute) and r.path.strip("/")}
    | {"/api", "/auth", "/docs", "/redoc", "/openapi.json"}
)


def first_segment(path: str) -> str:
    return "/" + path.lstrip("/").split("/", 1)[0]


def is_api_path(path: str) -> bool:
    return first_segment(path) in API_PREFIXES


def is_page_navigation(scope: Scope) -> bool:
    """Navegação do browser (HTML, sem token) para baixo de uma página da UI, ex. ``/admin/x``.

    ``/admin``, ``/users``, … são páginas e também prefixos da API. As rotas reais da API
    (``GET /admin/metrics``) coincidem antes do mount e continuam a ser a API; os pedidos da
    UI levam sempre ``Authorization``, por isso nunca chegam aqui como navegação.
    """
    headers = Headers(scope=scope)
    return (first_segment(scope["path"]) in UI_PATHS
            and "authorization" not in headers
            and "text/html" in headers.get("accept", ""))


class SpaMount(Mount):
    """Mount da SPA em ``/`` que só apanha GET/HEAD fora dos prefixos da API.

    Sem isto o mount em ``/`` ganhava a qualquer rota que só coincida no caminho (método
    diferente), e ``GET /ask`` devolvia o index.html em vez de 405. Exceção: uma navegação
    para baixo de uma página da UI (``/admin/x``) recebe a SPA em vez de um 404 JSON.
    """

    def matches(self, scope: Scope) -> tuple[Match, Scope]:
        if scope["type"] == "http" and (
                scope["method"] not in ("GET", "HEAD")
                or (is_api_path(scope["path"]) and not is_page_navigation(scope))):
            return Match.NONE, {}
        return super().matches(scope)


class SpaStaticFiles(StaticFiles):
    """Ficheiros do build Vite; navegações sem ficheiro (ex. /chat) devolvem index.html."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            # Só uma navegação do browser (Accept: text/html) recebe o shell; fetch/XHR leva 404.
            if "text/html" not in Headers(scope=scope).get("accept", ""):
                raise
            # ``path`` vem com o separador do SO (``assets\\x`` no Windows)
            rel = path.replace("\\", "/")
            # Em assets/ nunca há fallback: um ficheiro que não existe é 404 (e nunca o index.html
            # com cache de um ano). Fora de assets/, um nome com extensão também é 404.
            if rel == "assets" or rel.startswith("assets/"):
                raise
            name = rel.rsplit("/", 1)[-1]
            if name and "." in name:
                raise
            # Rotas do Vue Router (ex. /chat) → SPA shell
            return await super().get_response("index.html", scope)


# SPA em /. Só monta se houver build/fixture em APP_DIR (tem de ser a última rota).
if APP_DIR.is_dir() and (APP_DIR / "index.html").is_file():
    app.router.routes.append(SpaMount("/", app=SpaStaticFiles(directory=APP_DIR, html=True),
                                      name="vue_app"))
