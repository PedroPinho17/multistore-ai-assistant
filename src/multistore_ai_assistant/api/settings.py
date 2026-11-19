"""Definições: as de cada conta (idioma, tema, cor) e as da aplicação (só admin).

- ``user_settings``: uma linha por conta; ``NULL`` = segue a predefinição.
  Ficam na BD, por isso acompanham a conta noutro computador.
- ``app_settings``: chave → valor JSON, só com as chaves de ``APP_DEFAULTS``.
  Lidas em muitos pedidos (token, página inicial), por isso ficam em cache
  durante ``CACHE_SECONDS``; gravar limpa a cache.

Cores: 6 predefinidas, com tons afinados à mão para o tema claro e escuro, ou
uma personalizada em ``#rrggbb``. Para a personalizada, a UI calcula os tons a
partir da cor escolhida e ajusta-os até ao contraste AA (texto branco nos
botões, texto da cor sobre fundo claro/escuro), por isso nunca fica ilegível.
"""
import json
import logging
import re
import threading
import time

from multistore_ai_assistant.api.permissions import AccessDenied
from multistore_ai_assistant.db.pool import connection

log = logging.getLogger("multistore")

ACCENTS = ("green", "orange", "blue", "wine", "purple", "graphite")
HEX_COLOR = re.compile(r"^#[0-9a-f]{6}$")
LANGS = ("pt", "en", "es", "fr")
THEMES = ("light", "dark", "system")
SESSION_HOURS = (1, 2, 4, 8, 12, 24)

APP_DEFAULTS = {
    "default_accent": "green",
    "default_lang": "pt",
    "show_demo_accounts": True,
    "session_hours": 8,
}
# O que as páginas públicas (início, login) precisam de saber
PUBLIC_KEYS = ("default_accent", "default_lang", "show_demo_accounts")
CACHE_SECONDS = 30

_cache: dict = {"at": 0.0, "value": None}
_lock = threading.Lock()


class SettingsError(AccessDenied):
    """Valor inválido numa definição (400, com código para a UI traduzir)."""

    def __init__(self, message: str):
        super().__init__("bad_setting", message, 400, detail=message)


# ---------- validação (funções puras) ----------

def valid_accent(value) -> bool:
    """Uma das cores predefinidas ou uma cor personalizada ``#rrggbb`` (minúsculas)."""
    return isinstance(value, str) and (value in ACCENTS or bool(HEX_COLOR.match(value)))


def _normalize(key: str, value):
    """Cores em hexadecimal ficam sempre em minúsculas (``#0F7A5A`` → ``#0f7a5a``)."""
    if key in ("accent", "default_accent") and isinstance(value, str) and value.startswith("#"):
        return value.lower()
    return value

def check_user_changes(changes: dict) -> dict:
    """Valida ``{lang?, theme?, accent?}``; ``None`` volta à predefinição."""
    allowed = {"lang": LANGS, "theme": THEMES, "accent": None}
    out = {}
    for key, value in changes.items():
        if key not in allowed:
            raise SettingsError(f"Definição desconhecida: {key}")
        value = _normalize(key, value)
        ok = valid_accent(value) if key == "accent" else value in allowed[key]
        if value is not None and not ok:
            raise SettingsError(f"Valor inválido para {key}: {value!r}")
        out[key] = value
    return out


def check_app_changes(changes: dict) -> dict:
    """Valida as chaves de ``APP_DEFAULTS`` com os seus valores permitidos."""
    out = {}
    for key, value in changes.items():
        if key not in APP_DEFAULTS:
            raise SettingsError(f"Definição desconhecida: {key}")
        value = _normalize(key, value)
        ok = {
            "default_accent": valid_accent(value),
            "default_lang": value in LANGS,
            "show_demo_accounts": isinstance(value, bool),
            "session_hours": isinstance(value, int) and not isinstance(value, bool) and value in SESSION_HOURS,
        }[key]
        if not ok:
            raise SettingsError(f"Valor inválido para {key}: {value!r}")
        out[key] = value
    return out


# ---------- aplicação ----------

def get_app_settings() -> dict:
    """Definições da aplicação (predefinições + o que o admin mudou), com cache curta.

    Se a BD não responder, devolve as predefinições: a página inicial e o
    login nunca podem falhar por causa disto.
    """
    now = time.monotonic()
    cached = _cache["value"]
    if cached is not None and now - _cache["at"] < CACHE_SECONDS:
        return dict(cached)
    value = dict(APP_DEFAULTS)
    try:
        with connection("owner") as conn:
            for key, raw in conn.execute("SELECT key, value FROM app_settings").fetchall():
                if key in APP_DEFAULTS:
                    value[key] = raw          # o psycopg já devolve o jsonb descodificado
    except Exception:
        log.warning("Definições da aplicação indisponíveis; uso as predefinições", exc_info=True)
        return dict(APP_DEFAULTS)
    with _lock:
        _cache.update(at=now, value=value)
    return dict(value)


def clear_cache() -> None:
    with _lock:
        _cache.update(at=0.0, value=None)


def public_config() -> dict:
    """O que o browser precisa antes do login (cor, idioma, mostrar contas de demo)."""
    app = get_app_settings()
    return {k: app[k] for k in PUBLIC_KEYS}


def app_settings_details() -> dict:
    """Definições + quem mudou por último e quando (para a página do admin)."""
    app = get_app_settings()
    with connection("owner") as conn:
        row = conn.execute(
            """SELECT s.updated_at, u.username FROM app_settings s
               LEFT JOIN users u ON u.id = s.updated_by
               ORDER BY s.updated_at DESC LIMIT 1""").fetchone()
    return {"values": app, "updated_at": row[0].isoformat() if row else None,
            "updated_by": row[1] if row else None,
            "options": {"accents": list(ACCENTS), "langs": list(LANGS), "session_hours": list(SESSION_HOURS)}}


def update_app_settings(actor: dict, changes: dict) -> dict:
    """Grava as definições da aplicação (só o admin chega aqui)."""
    if actor.get("role") != "admin":
        raise AccessDenied("admin_only", "Só o admin muda as definições da aplicação.")
    changes = check_app_changes(changes)
    with connection("owner") as conn:
        for key, value in changes.items():
            conn.execute(
                """INSERT INTO app_settings (key, value, updated_by) VALUES (%s, %s::jsonb, %s)
                   ON CONFLICT (key) DO UPDATE
                   SET value = EXCLUDED.value, updated_by = EXCLUDED.updated_by, updated_at = now()""",
                (key, json.dumps(value), actor.get("id")))
    clear_cache()
    return app_settings_details()


# ---------- conta ----------

def get_user_settings(user: dict) -> dict:
    """``{lang, theme, accent}`` da conta (``None`` = predefinição)."""
    with connection("owner") as conn:
        row = conn.execute("SELECT lang, theme, accent FROM user_settings WHERE user_id = %s",
                           (user["id"],)).fetchone()
    return dict(zip(("lang", "theme", "accent"), row, strict=False)) if row else {"lang": None, "theme": None, "accent": None}


def update_user_settings(user: dict, changes: dict) -> dict:
    """Grava só os campos enviados; ``None`` apaga a escolha (volta à predefinição)."""
    changes = check_user_changes(changes)
    if changes:
        cols = list(changes)
        with connection("owner") as conn:
            conn.execute(
                f"""INSERT INTO user_settings (user_id, {", ".join(cols)}) VALUES (%s, {", ".join(["%s"] * len(cols))})
                    ON CONFLICT (user_id) DO UPDATE SET
                    {", ".join(f"{c} = EXCLUDED.{c}" for c in cols)}, updated_at = now()""",
                (user["id"], *changes.values()))
    return get_user_settings(user)
