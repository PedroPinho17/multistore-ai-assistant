"""Dependências partilhadas pelos routers: limites de pedidos e controlo de acesso."""
from fastapi import Depends, Request

from multistore_ai_assistant.api.auth import current_user
from multistore_ai_assistant.api.errors import ApiError
from multistore_ai_assistant.api.permissions import has_module
from multistore_ai_assistant.api.ratelimit import RateLimiter

login_limiter = RateLimiter(max_calls=10, per_seconds=300)    # 10 tentativas / 5 min por IP
ask_limiter = RateLimiter(max_calls=20, per_seconds=60)       # 20 perguntas / min por utilizador
conv_limiter = RateLimiter(max_calls=60, per_seconds=60)      # 60 pedidos às conversas / min por utilizador
password_limiter = RateLimiter(max_calls=5, per_seconds=900)  # 5 mudanças de password / 15 min por utilizador
users_limiter = RateLimiter(max_calls=30, per_seconds=60)     # 30 pedidos de gestão de contas / min
admin_limiter = RateLimiter(max_calls=30, per_seconds=60)     # 30 pedidos ao painel / min
explain_limiter = RateLimiter(max_calls=10, per_seconds=60)   # 10 explicações de SQL / min (custam tokens)
review_limiter = RateLimiter(max_calls=60, per_seconds=60)    # 60 pedidos de revisão / min (lista, testar, ensinar)

LIMITERS = (login_limiter, ask_limiter, conv_limiter, password_limiter, users_limiter, admin_limiter,
            explain_limiter, review_limiter)


def client_ip(request: Request) -> str:
    """IP do cliente (chave do rate limit de login)."""
    return request.client.host if request.client else "unknown"


def conversation_user(user: dict = Depends(current_user)) -> dict:
    """Utilizador autenticado + limite de pedidos para conversas, perfil e definições."""
    conv_limiter.check(user["username"])
    return user


def require_module(module: str, limiter: RateLimiter):
    """Dependência: utilizador autenticado, com o módulo e dentro do limite de pedidos."""
    def dependency(user: dict = Depends(current_user)) -> dict:
        if not has_module(user, module):
            raise ApiError("no_module", 403, module=module)
        limiter.check(user["username"])
        return user
    return dependency


def admin_user(user: dict = Depends(current_user)) -> dict:
    """Só a conta admin (definições da aplicação)."""
    if user["role"] != "admin":
        raise ApiError("admin_only", 403)
    admin_limiter.check(user["username"])
    return user
