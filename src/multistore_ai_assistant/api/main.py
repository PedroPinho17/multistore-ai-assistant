"""Aplicação FastAPI: monta os routers, os cabeçalhos de segurança e o formato dos erros.

As rotas estão em ``api/routes/`` (uma por área); as dependências partilhadas
(limites de pedidos, acesso por módulo) em ``api/deps.py``; os corpos dos
pedidos em ``api/schemas.py``. A lógica de negócio fica em ``assistant/``.
"""
import logging
import mimetypes
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from multistore_ai_assistant.api.errors import CATALOG, ApiError, request_lang, tr
from multistore_ai_assistant.api.routes import (
    admin,
    ask,
    auth,
    avatars,
    conversations,
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

INTENT_NAMES = {
    "xlmr": "XLM-RoBERTa (models/intent-xlmr)",
    "minilm": "MiniLM + LogReg (models/intent.joblib)",
    "none": "nenhum, decide sempre o LLM",
}


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


# Content-Security-Policy: scripts só do próprio site e do CDN fixo (Vue / Chart.js)
CSP = (
    "default-src 'self'; "
    "script-src 'self' https://cdn.jsdelivr.net 'unsafe-eval' 'unsafe-inline'; "
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
    response.headers["Content-Security-Policy"] = CSP
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    # API: nunca guardar em cache. Página e ficheiros estáticos: pode guardar, mas confirma sempre se mudou.
    # Uma rota que já escolheu a sua cache (as fotos de perfil, que nunca mudam de conteúdo) fica com ela.
    static = (request.url.path in ("/", "/favicon.ico") or request.url.path.startswith("/static/")
              or is_page_request(request))
    if "cache-control" not in response.headers:
        response.headers["Cache-Control"] = "no-cache" if static else "no-store"
    return response


for module in (auth, password, profile, avatars, ask, conversations, users, admin, review, examples, settings, pages):
    app.include_router(module.router)
app.mount("/static", StaticFiles(directory=WEB_DIR / "static", check_dir=False), name="static")
