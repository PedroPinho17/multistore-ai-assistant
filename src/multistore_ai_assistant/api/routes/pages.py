"""Página da UI, favicon e healthcheck.

A UI usa URLs normais (``/login``, ``/chat``, …) com a History API. Alguns destes
caminhos também são endpoints GET da API (``/users``, ``/profile``, ``/review``),
por isso a página só é servida a uma navegação do browser: pede HTML e não traz
token. Os pedidos da UI à API levam sempre ``Authorization: Bearer``.
"""
import os
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse, Response

_DEFAULT_APP_DIR = Path(__file__).resolve().parents[4] / "frontend" / "dist"
APP_DIR = Path(os.environ["VUE_APP_DIR"]) if os.environ.get("VUE_APP_DIR") else _DEFAULT_APP_DIR

router = APIRouter(include_in_schema=False)

# Páginas da UI (além de "/"); coincidem com as rotas do Vue Router
UI_PATHS = frozenset({"/login", "/reset-password", "/chat", "/dashboard", "/profile",
                      "/users", "/admin", "/settings", "/review"})


FRONTEND_NOT_BUILT = "frontend not built, run npm run build in frontend"


def index_page() -> Response:
    """O index.html da SPA; sem build (``frontend/dist``) dá 503 com a instrução, não um 500."""
    index = APP_DIR / "index.html"
    if not index.is_file():
        return JSONResponse(status_code=503, content={"detail": {"code": "frontend_not_built",
                                                                 "message": FRONTEND_NOT_BUILT}})
    return FileResponse(index, media_type="text/html")


def is_page_request(request: Request) -> bool:
    """True para uma navegação do browser para uma página da UI (não um pedido à API)."""
    path = request.url.path.rstrip("/") or "/"
    return (request.method in ("GET", "HEAD") and path in UI_PATHS
            and "authorization" not in request.headers
            and "text/html" in request.headers.get("accept", ""))


@router.get("/health")
def health():
    """Usado pelo healthcheck do Docker."""
    return {"ok": True}


@router.get("/favicon.ico")
def favicon():
    """Os browsers pedem sempre /favicon.ico, mesmo com o <link rel="icon">."""
    ico = APP_DIR / "favicon.ico"
    if not ico.is_file():
        ico = APP_DIR / "icons" / "favicon.ico"
    if not ico.is_file():
        return Response(status_code=404)
    return FileResponse(ico, media_type="image/x-icon")


@router.get("/")
def index():
    """Serve a SPA Vue (``frontend/dist/index.html``)."""
    return index_page()
