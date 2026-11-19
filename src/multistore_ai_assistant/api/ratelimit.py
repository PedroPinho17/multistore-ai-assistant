"""Rate limiting simples em memória (janela deslizante).

Chega para um só processo uvicorn. Com vários workers ou servidores,
usar Redis (p.ex. slowapi + redis) para partilhar os contadores.
"""
import time
from collections import defaultdict, deque
from threading import Lock

from multistore_ai_assistant.api.errors import ApiError


class RateLimiter:
    """Conta pedidos por chave (IP ou username) numa janela de tempo.

    Args:
        max_calls: Número máximo de pedidos permitidos na janela.
        per_seconds: Duração da janela em segundos.
    """

    def __init__(self, max_calls: int, per_seconds: int):
        self.max_calls = max_calls
        self.per_seconds = per_seconds
        self._calls: dict[str, deque] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str) -> None:
        """Regista um pedido; levanta 429 se a chave já esgotou o limite.

        Args:
            key: Identificador (IP no login, username nos outros endpoints).

        Raises:
            ApiError 429 (``rate_limited``): com cabeçalho ``Retry-After`` em segundos.
        """
        now = time.monotonic()
        with self._lock:
            calls = self._calls[key]
            # Remove timestamps fora da janela
            while calls and now - calls[0] > self.per_seconds:
                calls.popleft()
            if len(calls) >= self.max_calls:
                retry = int(self.per_seconds - (now - calls[0])) + 1
                err = ApiError("rate_limited", 429)
                err.headers = {"Retry-After": str(retry)}
                raise err
            calls.append(now)
