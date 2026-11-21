"""Funcionalidades por perfil (independentes dos módulos de cada conta).

A lista vive em ``role_features``. Cada processo guarda uma cópia em memória
(predefinições até a BD responder) para cada pedido não abrir uma ligação:

- a cópia é **por processo**: com vários workers, cada um tem a sua;
- um ``PUT /admin/features`` muda a BD e a memória do processo que o recebeu logo;
- os outros processos (ou uma alteração feita à mão na BD) apanham a mudança na
  releitura seguinte, no máximo ``REFRESH_SECONDS`` depois.

Predefinições (o que cada perfil já podia fazer):

- ``admin``: todas;
- ``imperador``: chat, previsão, encomendas, painel, revisão (rentabilidade) e contas;
- ``marca`` e ``loja``: chat, previsão, encomendas, painel e contas.

``users`` (a funcionalidade) é a gestão de contas; cada conta continua a precisar do módulo ``users``.
``admin`` (a funcionalidade) é o painel de observabilidade e a edição desta lista. É só do perfil
``admin`` e não se lhe tira: sem ela ninguém voltava a editar as permissões.
"""
import logging
import os
import threading
import time

from multistore_ai_assistant.api.errors import ApiError
from multistore_ai_assistant.api.permissions import ROLES

log = logging.getLogger("multistore")

FEATURES = ("chat", "forecast", "orders", "dashboard", "review", "users", "admin")
# Abrem o chat e as conversas; cada pergunta é verificada depois pela sua funcionalidade
CHAT_FEATURES = ("chat", "forecast", "orders")
REFRESH_SECONDS = 60

DEFAULT_ROLE_FEATURES = {
    "admin": set(FEATURES),
    "imperador": {"chat", "forecast", "orders", "dashboard", "review", "users"},
    "marca": {"chat", "forecast", "orders", "dashboard", "users"},
    "loja": {"chat", "forecast", "orders", "dashboard", "users"},
}

_table: dict[str, set[str]] = {}
_lock = threading.Lock()          # leitura da BD e escrita do PUT não se cruzam
_loaded_at = 0.0                  # time.monotonic() da última leitura (0 = nunca)


def _defaults() -> dict[str, set[str]]:
    return {role: set(feats) for role, feats in DEFAULT_ROLE_FEATURES.items()}


_table.update(_defaults())


def _from_db_enabled() -> bool:
    return os.getenv("ROLE_FEATURES_FROM_DB", "1") == "1"


def reset_defaults() -> None:
    """Volta às predefinições (testes)."""
    global _loaded_at
    _table.clear()
    _table.update(_defaults())
    _loaded_at = 0.0


def _maybe_refresh() -> None:
    """Relê a BD se a cópia tiver mais de ``REFRESH_SECONDS``. Nunca bloqueia nem falha o pedido."""
    if not _from_db_enabled() or time.monotonic() - _loaded_at < REFRESH_SECONDS:
        return
    if not _lock.acquire(blocking=False):      # outro pedido já está a reler
        return
    try:
        if time.monotonic() - _loaded_at >= REFRESH_SECONDS:
            _load_locked()
    except Exception:
        log.warning("Funcionalidades por perfil: releitura falhou, fica a cópia atual", exc_info=True)
        _touch()                                # não tenta outra vez a cada pedido
    finally:
        _lock.release()


def _touch() -> None:
    global _loaded_at
    _loaded_at = time.monotonic()


def features_for(role: str) -> list[str]:
    """Funcionalidades do perfil, na ordem de ``FEATURES``."""
    _maybe_refresh()
    owned = _table.get(role, set())
    return [f for f in FEATURES if f in owned]


def has_feature(user: dict, feature: str) -> bool:
    """True se o perfil do utilizador tem a funcionalidade.

    ``user["features"]`` (lista explícita, p.ex. num teste) ganha à tabela.
    Sem perfil, não tem nenhuma.
    """
    listed = user.get("features")
    if listed is not None:
        return feature in listed
    _maybe_refresh()
    return feature in _table.get(user.get("role") or "", set())


def has_any_feature(user: dict, features: tuple[str, ...] | list[str]) -> bool:
    return any(has_feature(user, feature) for feature in features)


def user_features(user: dict) -> list[str]:
    """Lista que o ``/me`` e o login enviam à UI."""
    listed = user.get("features")
    if listed is not None:
        return [f for f in FEATURES if f in listed]
    return features_for(user.get("role") or "")


def _validate(role: str, features: list[str]) -> list[str]:
    if role not in ROLES:
        raise ApiError("bad_role", 400)
    unknown = [f for f in features if f not in FEATURES]
    if unknown:
        raise ApiError("bad_feature", 400, feature=", ".join(sorted(unknown)))
    chosen = [f for f in FEATURES if f in set(features)]
    if role == "admin" and "admin" not in chosen:
        raise ApiError("admin_feature_locked", 400)
    if role != "admin" and "admin" in chosen:
        raise ApiError("admin_feature_admin_only", 400)
    return chosen


def set_role_features(role: str, features: list[str]) -> list[str]:
    """Substitui as funcionalidades de um perfil (BD + memória deste processo, logo)."""
    chosen = _validate(role, features)
    with _lock:
        _write(role, chosen)
        _table[role] = set(chosen)
    return chosen


def matrix() -> dict:
    """Todas as funcionalidades e o que cada perfil tem agora."""
    return {"features": list(FEATURES), "roles": {role: features_for(role) for role in ROLES}}


def load_from_db() -> None:
    """Substitui a memória pelas linhas da BD. Com ``ROLE_FEATURES_FROM_DB=0``, não faz nada.

    Se a tabela ainda não existir, a exceção sobe (o arranque fica com as predefinições).
    """
    if not _from_db_enabled():
        return
    with _lock:
        _load_locked()


def _load_locked() -> None:
    """Lê a BD e troca a tabela inteira num só passo (quem lê a meio nunca vê um dict vazio)."""
    global _table
    from multistore_ai_assistant.db.pool import connection

    with connection() as conn:
        rows = conn.execute("SELECT role, feature FROM role_features").fetchall()
    if not rows:
        log.warning("role_features está vazia: a usar as permissões por defeito")
        _table = _defaults()
        _touch()
        return
    loaded: dict[str, set[str]] = {role: set() for role in ROLES}
    for role, feature in rows:
        if role in loaded and feature in FEATURES:
            loaded[role].add(feature)
    loaded["admin"].add("admin")
    for role in ROLES:
        if role != "admin":
            loaded[role].discard("admin")
    _table = loaded
    _touch()
    log.debug("Funcionalidades por perfil carregadas da BD")


def _write(role: str, features: list[str]) -> None:
    from multistore_ai_assistant.db.pool import connection

    with connection() as conn:
        conn.execute("DELETE FROM role_features WHERE role = %s", (role,))
        conn.executemany(
            "INSERT INTO role_features (role, feature) VALUES (%s, %s)",
            [(role, feature) for feature in features],
        )
