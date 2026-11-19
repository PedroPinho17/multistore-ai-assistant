"""Métricas de cada pergunta: tempo, intenção, tentativas de SQL e tokens do LLM.

Um ``Trace`` vive numa ``ContextVar`` durante o pedido. As funções que chamam
o LLM registam os tokens (``record_llm``) e o ``ask`` regista a intenção e as
tentativas de SQL, sem receberem o Trace como argumento.

Fora de um pedido (scripts, CLI, testes) não há Trace e estas funções não
fazem nada.
"""
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field


@dataclass
class Trace:
    """O que aconteceu durante uma pergunta (vai para a tabela ``request_log``)."""
    started: float = field(default_factory=time.perf_counter)
    intent: str | None = None
    confidence: float | None = None
    sql_attempts: int = 0
    sql_failed: bool = False
    error: str | None = None
    llm_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cache_hit: bool = False

    def duration_ms(self) -> int:
        """Milissegundos desde o início do pedido."""
        return round((time.perf_counter() - self.started) * 1000)


_current: ContextVar[Trace | None] = ContextVar("multistore_trace", default=None)


@contextmanager
def trace():
    """Abre um Trace para o pedido atual: ``with trace() as t: ...``."""
    t = Trace()
    token = _current.set(t)
    try:
        yield t
    finally:
        _current.reset(token)


def current() -> Trace | None:
    """Trace do pedido atual (``None`` fora de um pedido)."""
    return _current.get()


def record_llm(response) -> None:
    """Soma os tokens de uma resposta da API do LLM (formato OpenAI)."""
    t = current()
    if t is None:
        return
    usage = getattr(response, "usage", None)
    t.llm_calls += 1
    t.prompt_tokens += int(getattr(usage, "prompt_tokens", 0) or 0)
    t.completion_tokens += int(getattr(usage, "completion_tokens", 0) or 0)


def record_intent(intent: str | None, confidence: float | None) -> None:
    """Etiqueta e confiança do classificador local."""
    t = current()
    if t is not None:
        t.intent = intent
        t.confidence = None if confidence is None else round(float(confidence), 4)


def record_sql_attempt(error: Exception | None = None) -> None:
    """Uma tentativa de SQL; com ``error`` quando a query falhou (validador ou BD)."""
    t = current()
    if t is None:
        return
    t.sql_attempts += 1
    if error is not None:
        t.sql_failed = True
        t.error = f"{type(error).__name__}: {error}"[:500]


def record_cache_hit() -> None:
    """A resposta usou SQL da cache (pergunta com a mesma chave) (sem chamar o LLM para gerar SQL)."""
    t = current()
    if t is not None:
        t.cache_hit = True
