"""Página da UI, favicon e healthcheck.

A UI usa URLs normais (``/login``, ``/chat``, …) com a History API. Alguns destes
caminhos também são endpoints GET da API (``/users``, ``/profile``, ``/review``),
por isso a página só é servida a uma navegação do browser: pede HTML e não traz
token. Os pedidos da UI à API levam sempre ``Authorization: Bearer``.
"""
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

WEB_DIR = Path(__file__).resolve().parents[4] / "web"
router = APIRouter(include_in_schema=False)

# Páginas da UI (além de "/"); têm de coincidir com ROUTES em web/static/js/app.js
UI_PATHS = frozenset({"/login", "/reset-password", "/chat", "/dashboard", "/profile",
                      "/users", "/admin", "/settings", "/review"})


def index_page() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html", media_type="text/html")


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
    return FileResponse(WEB_DIR / "static" / "icons" / "favicon.ico", media_type="image/x-icon")


@router.get("/")
def index():
    """Serve a UI Vue (``web/index.html``)."""
    return index_page()
