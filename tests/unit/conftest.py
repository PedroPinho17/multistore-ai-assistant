"""Testes unitários: a BD é sempre simulada.

``auth.load_user`` (chamado em cada pedido autenticado) passa a ler de um
dicionário em memória; o registo de pedidos e as avaliações também.
Um teste pode mudar ``fake_users`` para simular contas desativadas, etc.
"""
import os

import pytest

os.environ["ROLE_FEATURES_FROM_DB"] = "0"

from multistore_ai_assistant.api import auth
from multistore_ai_assistant.api import features as role_features
from tests.conftest import ADMIN, IMPERADOR, LOJA, MARCA, patch_route

REAL_LOAD_USER = auth.load_user


@pytest.fixture(autouse=True)
def reset_role_features():
    """Cada teste parte das funcionalidades por defeito de cada perfil."""
    role_features.reset_defaults()
    yield
    role_features.reset_defaults()


@pytest.fixture(autouse=True)
def fake_users(monkeypatch):
    """Contas conhecidas pelo ``current_user`` (sem BD)."""
    users = {u["username"]: dict(u) for u in (ADMIN, IMPERADOR, MARCA, LOJA)}
    monkeypatch.setattr(auth, "load_user", lambda name: dict(users[name]) if name in users else None)
    return users


@pytest.fixture(autouse=True)
def fake_request_log(monkeypatch):
    """Registo de pedidos em memória: cada pergunta recebe um id sequencial."""
    saved = []

    def save(t, user, question, lang, kind, conversation_id=None):
        saved.append({"user": user["username"], "question": question, "lang": lang, "kind": kind,
                      "conversation_id": conversation_id, "llm_calls": t.llm_calls,
                      "sql_attempts": t.sql_attempts, "error": t.error})
        return len(saved)
    patch_route(monkeypatch, "save_request", save)
    return saved


@pytest.fixture(autouse=True)
def fake_me_details(monkeypatch):
    """Foto e marca da conta (o /me junta-as ao perfil) sem ir à BD."""
    patch_route(monkeypatch, "me_details", lambda user: {"avatar_url": None, "brand_name": None})


@pytest.fixture(autouse=True)
def fake_settings(monkeypatch):
    """Definições em memória: as da aplicação são as predefinições; as da conta, vazias."""
    from multistore_ai_assistant.api import settings as st
    app = dict(st.APP_DEFAULTS)
    monkeypatch.setattr(st, "get_app_settings", lambda: dict(app))
    monkeypatch.setattr(st, "get_user_settings", lambda user: {"lang": None, "theme": None, "accent": None})
    return app


@pytest.fixture(autouse=True)
def no_semantic_cache(monkeypatch):
    """Sem cache de SQL nos testes unitários (precisa da BD e do modelo de embeddings)."""
    from multistore_ai_assistant.assistant import ask as ask_mod
    monkeypatch.setattr(ask_mod, "cache_lookup", lambda q, u: None)
    monkeypatch.setattr(ask_mod, "cache_store", lambda q, s, u: None)
