"""Envio de email por SMTP (hoje só o link de recuperação de password).

Configuração no .env (tudo opcional; sem ``SMTP_HOST`` não se envia nada):

- ``SMTP_HOST``, ``SMTP_PORT`` (587), ``SMTP_USER``, ``SMTP_PASSWORD``
- ``SMTP_SECURITY``: ``starttls`` (predefinição), ``ssl`` (porta 465) ou ``none`` (só em testes locais)
- ``SMTP_FROM``: remetente (``Multistore AI <no-reply@exemplo.pt>``); por defeito ``SMTP_USER``
- ``APP_URL``: endereço público da app, usado no link (``http://localhost:8001``)

Sem SMTP, ou se o envio falhar, só fica um aviso no log (nunca o token nem o link):
a resposta pública ao pedido de recuperação é sempre a mesma.
"""
import logging
import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

log = logging.getLogger("multistore")
TIMEOUT = 10

RESET_TEXT = {
    "pt": ("Repor a palavra-passe · Multistore AI",
           "Olá {username},\n\nPediste para repor a palavra-passe da tua conta no Multistore AI.\n"
           "Abre este link para escolher uma nova (válido durante {minutes} minutos, só pode ser usado uma vez):\n\n"
           "{link}\n\nSe não foste tu, ignora este email: a tua palavra-passe não muda.\n"),
    "en": ("Reset your password · Multistore AI",
           "Hi {username},\n\nYou asked to reset the password of your Multistore AI account.\n"
           "Open this link to choose a new one (valid for {minutes} minutes, single use):\n\n"
           "{link}\n\nIf this wasn't you, ignore this email: your password stays the same.\n"),
    "es": ("Restablecer la contraseña · Multistore AI",
           "Hola {username}:\n\nHas pedido restablecer la contraseña de tu cuenta de Multistore AI.\n"
           "Abre este enlace para elegir una nueva (válido durante {minutes} minutos, un solo uso):\n\n"
           "{link}\n\nSi no has sido tú, ignora este correo: tu contraseña no cambia.\n"),
    "fr": ("Réinitialiser le mot de passe · Multistore AI",
           "Bonjour {username},\n\nVous avez demandé à réinitialiser le mot de passe de votre compte Multistore AI.\n"
           "Ouvrez ce lien pour en choisir un nouveau (valable {minutes} minutes, usage unique) :\n\n"
           "{link}\n\nSi ce n'était pas vous, ignorez cet e-mail : votre mot de passe ne change pas.\n"),
}


def smtp_configured() -> bool:
    return bool(os.getenv("SMTP_HOST", "").strip())


def app_url() -> str:
    return (os.getenv("APP_URL") or "http://localhost:8001").rstrip("/")


def build_reset_email(to: str, username: str, link: str, minutes: int, lang: str = "pt") -> EmailMessage:
    subject, body = RESET_TEXT.get(lang, RESET_TEXT["pt"])
    sender = os.getenv("SMTP_FROM") or os.getenv("SMTP_USER") or "no-reply@localhost"
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender if "<" in sender else formataddr(("Multistore AI", sender))
    msg["To"] = to
    msg["Message-ID"] = make_msgid(domain=sender.rsplit("@", 1)[-1].strip(">") or "localhost")
    msg.set_content(body.format(username=username, link=link, minutes=minutes))
    return msg


def send(msg: EmailMessage) -> bool:
    """Envia; devolve False (com aviso no log) se não houver SMTP ou o envio falhar."""
    if not smtp_configured():
        log.warning("SMTP não configurado (SMTP_HOST): email '%s' não enviado", msg["Subject"])
        return False
    host = os.environ["SMTP_HOST"].strip()
    security = os.getenv("SMTP_SECURITY", "starttls").strip().lower()
    port = int(os.getenv("SMTP_PORT") or (465 if security == "ssl" else 587))
    user, password = os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD")
    context = ssl.create_default_context()
    try:
        if security == "ssl":
            server = smtplib.SMTP_SSL(host, port, timeout=TIMEOUT, context=context)
        else:
            server = smtplib.SMTP(host, port, timeout=TIMEOUT)
        with server:
            if security == "starttls":
                server.starttls(context=context)
            if user and password:
                server.login(user, password)
            server.send_message(msg)
        return True
    except (OSError, smtplib.SMTPException) as e:
        log.error("Falha a enviar email '%s' por SMTP (%s): %s", msg["Subject"], host, type(e).__name__)
        return False
