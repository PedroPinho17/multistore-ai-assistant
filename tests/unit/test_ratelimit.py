import pytest

from multistore_ai_assistant.api import ratelimit
from multistore_ai_assistant.api.errors import ApiError
from multistore_ai_assistant.api.ratelimit import RateLimiter


@pytest.fixture
def clock(monkeypatch):
    """Relógio controlado pelo teste."""
    now = {"t": 1000.0}
    monkeypatch.setattr(ratelimit.time, "monotonic", lambda: now["t"])
    return now


def test_allows_up_to_the_limit(clock):
    limiter = RateLimiter(max_calls=3, per_seconds=60)
    for _ in range(3):
        limiter.check("ana")


def test_blocks_after_the_limit_with_retry_after(clock):
    limiter = RateLimiter(max_calls=2, per_seconds=60)
    limiter.check("ana")
    clock["t"] += 10
    limiter.check("ana")
    with pytest.raises(ApiError) as exc:
        limiter.check("ana")
    assert exc.value.status == 429
    assert exc.value.headers["Retry-After"] == "51"   # 60 - 10 + 1


def test_keys_are_independent(clock):
    limiter = RateLimiter(max_calls=1, per_seconds=60)
    limiter.check("ana")
    limiter.check("rui")          # outro utilizador / IP não é afetado
    with pytest.raises(ApiError):
        limiter.check("ana")


def test_window_slides(clock):
    limiter = RateLimiter(max_calls=1, per_seconds=60)
    limiter.check("ana")
    clock["t"] += 61
    limiter.check("ana")          # a chamada antiga já saiu da janela


def test_blocked_calls_do_not_count(clock):
    limiter = RateLimiter(max_calls=1, per_seconds=60)
    limiter.check("ana")
    for _ in range(5):
        with pytest.raises(ApiError):
            limiter.check("ana")
    clock["t"] += 61
    limiter.check("ana")          # insistir não prolonga o bloqueio
