"""Recuperação de password por email (públicas, sem sessão): ``/password/forgot`` e ``/password/reset``."""
import logging
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Request

from multistore_ai_assistant.api import mailer
from multistore_ai_assistant.api.deps import client_ip, forgot_limiter, reset_limiter
from multistore_ai_assistant.api.password_reset import TOKEN_MINUTES, request_reset, reset_password
from multistore_ai_assistant.api.schemas import ForgotIn, ResetIn

router = APIRouter(prefix="/password", tags=["password"])
log = logging.getLogger("multistore")


def send_reset_link(email: str, username: str, token: str, lang: str) -> None:
    """Corre depois da resposta (BackgroundTasks): o tempo de resposta não revela se a conta existe.

    O token vai no fragmento (``#token=``): o browser nunca o envia ao servidor, por isso
    não fica nos logs de acesso, em proxies nem no cabeçalho Referer.
    """
    link = f"{mailer.app_url()}/reset-password#token={quote(token)}"
    sent = mailer.send(mailer.build_reset_email(email, username, link, TOKEN_MINUTES, lang))
    log.info("Recuperação de password pedida para %r (email %s)", username, "enviado" if sent else "NÃO enviado")


@router.post("/forgot", status_code=202)
def forgot(body: ForgotIn, request: Request, background: BackgroundTasks):
    """Pede um link de recuperação. A resposta é sempre a mesma, exista a conta ou não.

    Só as contas de demonstração (públicas) recebem um erro claro (``reset_demo``).
    """
    forgot_limiter.check(client_ip(request))
    forgot_limiter.check("login:" + body.login.strip().lower())       # não inundar a caixa de uma pessoa
    found = request_reset(body.login, client_ip(request))
    if found:
        background.add_task(send_reset_link, found["email"], found["username"], found["token"], body.lang)
    return {"ok": True}


@router.post("/reset")
def reset(body: ResetIn, request: Request):
    """Define a nova password com o token do link (uso único, expira em ``TOKEN_MINUTES``)."""
    reset_limiter.check(client_ip(request))
    username = reset_password(body.token, body.new_password)
    log.info("Password reposta por link de recuperação: %r", username)
    return {"ok": True}
