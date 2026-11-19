"""Página da UI, favicon e healthcheck."""
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

WEB_DIR = Path(__file__).resolve().parents[4] / "web"
router = APIRouter(include_in_schema=False)


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
    return FileResponse(WEB_DIR / "index.html")
