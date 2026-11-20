"""Cliente do LLM com chave de reserva.

``GROQ_API_KEY`` é a chave principal; ``GROQ_API_KEY_FALLBACK`` (opcional) é usada
quando a principal esgota a quota (``RateLimitError`` / HTTP 429, p.ex. o limite
diário de tokens da Groq). A chave esgotada fica de lado durante o tempo que o
fornecedor indica ("try again in 14m56s", no mínimo ``MIN_COOLDOWN``) e depois
volta a ser a primeira a tentar.

A interface é a do SDK da OpenAI (``client.chat.completions.create(...)``, também
em streaming), por isso o resto do código não muda. As chaves nunca vão para os logs.
"""
import logging
import os
import re
import threading
import time
from collections.abc import Callable, Sequence

from openai import APIStatusError, OpenAI, RateLimitError

log = logging.getLogger("multistore")

MIN_COOLDOWN = 300.0          # segundos com uma chave de lado depois de esgotar a quota
KEY_NAMES = ("principal", "reserva")
_WAIT = re.compile(r"try again in (?:(\d+)h)?(?:(\d+)m)?(?:([\d.]+)s)?", re.I)


def is_quota_error(error: Exception) -> bool:
    """Quota/limite esgotado: vale a pena tentar com a outra chave."""
    if isinstance(error, RateLimitError):
        return True
    if isinstance(error, APIStatusError):
        text = str(error).lower()
        return error.status_code == 429 or "quota" in text or "tokens per day" in text
    return False


def retry_after(error: Exception) -> float:
    """Segundos até a chave voltar a ter quota (pelo texto do erro), nunca menos que MIN_COOLDOWN."""
    match = _WAIT.search(str(error))
    if not match or not any(match.groups()):
        return MIN_COOLDOWN
    h, m, s = (float(g) if g else 0.0 for g in match.groups())
    return max(MIN_COOLDOWN, h * 3600 + m * 60 + s)


class _Completions:
    def __init__(self, owner: "FallbackClient"):
        self._owner = owner

    def create(self, **kwargs):
        return self._owner._call(kwargs)


class _Chat:
    def __init__(self, owner: "FallbackClient"):
        self.completions = _Completions(owner)


class FallbackClient:
    """Tenta as chaves por ordem; passa à seguinte só em erros de quota."""

    def __init__(self, keys: Sequence[str], base_url: str | None = None,
                 factory: Callable[..., OpenAI] = OpenAI, clock: Callable[[], float] = time.monotonic):
        keys = list(dict.fromkeys(k.strip() for k in keys if k and k.strip()))   # sem vazias nem repetidas
        if not keys:
            raise RuntimeError("Falta GROQ_API_KEY no .env")
        # Com reserva, a principal não faz as retentativas do SDK (esperaria minutos antes de mudar)
        self._clients = [factory(api_key=k, base_url=base_url, **({"max_retries": 0} if i < len(keys) - 1 else {}))
                         for i, k in enumerate(keys)]
        self._blocked_until = [0.0] * len(keys)
        self._clock = clock
        self._lock = threading.Lock()
        self.chat = _Chat(self)

    @property
    def keys(self) -> int:
        return len(self._clients)

    def _order(self) -> list[int]:
        """Chaves disponíveis primeiro (pela ordem do .env); as de lado no fim, como último recurso."""
        now = self._clock()
        with self._lock:
            ready = [i for i, until in enumerate(self._blocked_until) if until <= now]
        return ready + [i for i in range(self.keys) if i not in ready]

    def _call(self, kwargs: dict):
        last: Exception | None = None
        for i in self._order():
            try:
                return self._clients[i].chat.completions.create(**kwargs)
            except Exception as e:
                if not is_quota_error(e):
                    raise
                last = e
                wait = retry_after(e)
                with self._lock:
                    self._blocked_until[i] = self._clock() + wait
                if self.keys > 1:
                    log.warning("Quota esgotada na chave %s do LLM; fica de lado %.0f s",
                                KEY_NAMES[min(i, len(KEY_NAMES) - 1)], wait)
        raise last


def llm_client() -> FallbackClient:
    """Cliente a partir do .env: GROQ_API_KEY, GROQ_API_KEY_FALLBACK (opcional) e LLM_BASE_URL."""
    return FallbackClient([os.environ.get("GROQ_API_KEY", ""), os.environ.get("GROQ_API_KEY_FALLBACK", "")],
                          base_url=os.environ.get("LLM_BASE_URL"), factory=OpenAI)
