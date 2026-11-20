"""Aplicação FastAPI: monta os routers, os cabeçalhos de segurança e o formato dos erros.

As rotas estão em ``api/routes/`` (uma por área); as dependências partilhadas
(limites de pedidos, acesso por módulo) em ``api/deps.py``; os corpos dos
pedidos em ``api/schemas.py``. A lógica de negócio fica em ``assistant/``.
"""
import logging
import mimetypes
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
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
from multistore_ai_assistant.api.routes.pages import WEB_DIR, index_page, is_page_request
from multistore_ai_assistant.db.pool import close_pools
from multistore_ai_assistant.intent.predict import backend as intent_backend

mimetypes.add_type("application/manifest+json", ".webmanifest")   # o Windows não o conhece
mimetypes.add_type("image/svg+xml", ".svg")

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("multistore")

# SPA Vue (Vite) em frontend/dist — servida em /app; a UI antiga em web/ fica em /
# VUE_APP_DIR: nos testes aponta para tests/fixtures/vue_dist
_DEFAULT_APP_DIR = Path(__file__).resolve().parents[3] / "frontend" / "dist"
APP_DIR = Path(os.environ["VUE_APP_DIR"]) if os.environ.get("VUE_APP_DIR") else _DEFAULT_APP_DIR


INTENT_NAMES = {
    "xlmr": "XLM-RoBERTa (models/intent-xlmr)",
    "minilm": "MiniLM + LogReg (models/intent.joblib)",
    "none": "nenhum, decide sempre o LLM",
}


def is_vue_app_path(path: str) -> bool:
    """True só para /app e /app/… (não para /appointments)."""
    return path == "/app" or path.startswith("/app/")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Arranque: regista o classificador ativo. Fim: fecha os pools de ligações."""
    log.info("Classificador de intenção: %s", INTENT_NAMES[intent_backend()])
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


# UI antiga (CDN Vue / Chart.js): precisa de jsDelivr, eval e scripts inline
CSP = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.jsdelivr.net 'unsafe-eval' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)

# SPA Vite em /app: só scripts do próprio origin (theme-boot.js + bundles)
CSP_APP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)


@app.middleware("http")
async def ui_pages(request: Request, call_next):
    """``/chat``, ``/login``, … abertos no browser devolvem a UI (o router Vue escolhe a página).

    Fica registado antes de ``security_headers``, por isso a página também leva os cabeçalhos.
    """
    if is_page_request(request):
        return index_page()
    return await call_next(request)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """Aplica cabeçalhos de segurança a todas as respostas HTTP."""
    response = await call_next(request)
    path = request.url.path
    response.headers["Content-Security-Policy"] = CSP_APP if is_vue_app_path(path) else CSP
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    # API: never store. /app/assets/*: só os ficheiros reais (200, ou 304 a revalidar um deles)
    # são immutable; lá não há fallback para o index.html, e um 404 fica no-cache.
    if "cache-control" not in response.headers:
        if path.startswith("/app/assets/") and response.status_code in (200, 304):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif (path in ("/", "/favicon.ico") or path.startswith("/static/")
              or is_vue_app_path(path) or is_page_request(request)):
            response.headers["Cache-Control"] = "no-cache"
        else:
            response.headers["Cache-Control"] = "no-store"
    return response


for module in (auth, password, profile, avatars, ask, conversations, dashboard,
               users, admin, review, examples, settings, pages):
    app.include_router(module.router)
app.mount("/static", StaticFiles(directory=WEB_DIR / "static", check_dir=False), name="static")


class SpaStaticFiles(StaticFiles):
    """Ficheiros do build Vite; caminhos sem ficheiro (ex. /app/chat) devolvem index.html."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
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
            # Rotas do Vue Router (ex. /app/chat) → SPA shell
            return await super().get_response("index.html", scope)


# Nova UI (Vue + Vite). Só monta se houver build/fixture em APP_DIR.
if APP_DIR.is_dir() and (APP_DIR / "index.html").is_file():
    app.mount("/app", SpaStaticFiles(directory=APP_DIR, html=True), name="vue_app")
