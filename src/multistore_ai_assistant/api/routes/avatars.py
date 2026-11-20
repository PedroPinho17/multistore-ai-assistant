"""Foto de perfil: ``POST``/``DELETE /me/avatar`` (a própria conta) e ``GET /avatars/{ficheiro}``.

O upload é o ficheiro em bruto no corpo do pedido, com ``Content-Type`` image/png,
image/jpeg ou image/webp (sem multipart)::

    curl -X POST /me/avatar -H "Authorization: Bearer …" -H "Content-Type: image/png" --data-binary @foto.png

As fotos só são servidas a quem tem sessão iniciada. Como um ``<img src>`` não envia o
token, a UI pede-as com ``fetch`` (cabeçalho ``Authorization``) e mostra-as como data URL.
"""
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from multistore_ai_assistant.api.auth import current_user
from multistore_ai_assistant.api.avatars import (
    MAX_BYTES,
    AvatarError,
    avatar_file,
    check_content_type,
    delete_avatar,
    save_avatar,
    too_big,
)
from multistore_ai_assistant.api.deps import conversation_user
from multistore_ai_assistant.api.errors import ApiError
from multistore_ai_assistant.api.permissions import require_not_demo

router = APIRouter(tags=["profile"])
log = logging.getLogger("multistore")


async def _read_body(request: Request) -> bytes:
    """Corpo do pedido, parando assim que passa de ``MAX_BYTES`` (não o guarda todo em memória)."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BYTES:
        raise too_big()
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > MAX_BYTES:
            raise too_big()
    return bytes(body)


@router.post("/me/avatar")
async def upload_avatar(request: Request, user: dict = Depends(conversation_user)):
    """Guarda a foto da própria conta: PNG/JPEG/WebP até 2 MB, validada e convertida em WebP 256×256."""
    require_not_demo(user)                # a foto da conta de demo aparecia a todos os visitantes
    try:
        check_content_type(request.headers.get("content-type"))
        raw = await _read_body(request)
        url = await run_in_threadpool(save_avatar, user["username"], raw)
    except AvatarError as e:
        raise ApiError(e.code, e.status, str(e)) from None
    log.info("Foto de perfil alterada por %r", user["username"])
    return {"avatar_url": url}


@router.delete("/me/avatar")
def remove_avatar(user: dict = Depends(conversation_user)):
    """Tira a foto da própria conta (a UI volta às iniciais)."""
    require_not_demo(user)
    delete_avatar(user["username"])
    return {"avatar_url": None}


@router.get("/avatars/{name}")
def get_avatar(name: str, _user: dict = Depends(current_user)):
    """Ficheiro de uma foto (só com sessão iniciada). O nome é um UUID: nunca muda de conteúdo."""
    path = avatar_file(name)
    if not path:
        raise ApiError("avatar_not_found", 404)
    return FileResponse(path, media_type="image/webp",
                        headers={"Cache-Control": "private, max-age=31536000, immutable"})
