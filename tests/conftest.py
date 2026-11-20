"""Configuração comum dos testes.

- Testes unitários: não precisam de base de dados nem de LLM (tudo com mocks).
- @pytest.mark.integration: precisam do Postgres a correr (docker compose up -d).
  São saltados automaticamente se a base de dados não responder.
- @pytest.mark.model: precisam dos modelos treinados em models/.
"""
import os

from dotenv import load_dotenv

# 1.º o .env real (para os testes de integração); depois valores por defeito,
# para os testes unitários correrem num computador/CI sem .env
load_dotenv()
for key, value in {
    "GROQ_API_KEY": "test-key",
    "LLM_BASE_URL": "http://localhost:9/v1",
    "LLM_MODEL": "test-model",
    "JWT_SECRET": "test-secret-with-more-than-32-characters-xx",
    "DATABASE_URL": "postgresql://multistore:x@localhost:5433/multistore",
    "READONLY_DATABASE_URL": "postgresql://assistente:x@localhost:5433/multistore",
}.items():
    os.environ.setdefault(key, value)

import pytest  # noqa: E402

from multistore_ai_assistant.api import deps  # noqa: E402
from multistore_ai_assistant.api import review as review_logic  # noqa: E402
from multistore_ai_assistant.api.routes import (  # noqa: E402
    admin,
    ask,
    auth,
    avatars,
    conversations,
    pages,
    profile,
    review,
    settings,
    users,
)

LIMITERS = deps.LIMITERS
# review_logic: o /feedback valida o SQL com api.review.teachable_sql (run_query, add_example)
ROUTE_MODULES = (auth, profile, avatars, ask, conversations, users, admin, review, settings, pages, review_logic)


def patch_route(mp, name: str, value) -> None:
    """Substitui ``name`` em todos os routers que o usam (cada um importa o seu)."""
    hits = [m for m in ROUTE_MODULES if hasattr(m, name)]
    assert hits, f"nenhum router usa {name!r}"
    for module in hits:
        mp.setattr(module, name, value)


@pytest.fixture(autouse=True)
def reset_rate_limits():
    """Cada teste começa com os contadores de rate limit a zero."""
    for limiter in LIMITERS:
        limiter._calls.clear()
    yield
    for limiter in LIMITERS:
        limiter._calls.clear()


# Perfis como saem de auth.load_user (os módulos são os efetivos de cada perfil)
ADMIN = {"id": 99, "username": "dono", "role": "admin", "brand_id": None, "store_id": None,
         "modules": ["sql", "forecast", "orders", "teach", "users", "observability"]}
IMPERADOR = {"id": 1, "username": "pedro", "role": "imperador", "brand_id": None, "store_id": None,
             "modules": ["sql", "forecast", "orders", "teach", "users"]}
MARCA = {"id": 2, "username": "gestor.burgerlab", "role": "marca", "brand_id": 1, "store_id": None,
         "modules": ["sql", "forecast", "orders", "users"]}
LOJA = {"id": 3, "username": "gerente.maia", "role": "loja", "brand_id": None, "store_id": 1,
        "modules": ["sql", "forecast", "orders", "users"]}
