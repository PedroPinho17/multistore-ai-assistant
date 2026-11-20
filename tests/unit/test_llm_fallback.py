"""Chave de reserva do LLM (GROQ_API_KEY_FALLBACK), com clientes falsos: sem rede nem chaves reais."""
import httpx
import pytest
from openai import APIStatusError, AuthenticationError, RateLimitError

from multistore_ai_assistant.assistant import llm
from multistore_ai_assistant.assistant.llm import MIN_COOLDOWN, FallbackClient, is_quota_error, retry_after

REQUEST = httpx.Request("POST", "https://llm.test/v1/chat/completions")


def quota_error(text="Rate limit reached on tokens per day (TPD): Limit 200000. Please try again in 14m56.8s."):
    return RateLimitError(text, response=httpx.Response(429, request=REQUEST), body=None)


def status_error(status, text, cls=APIStatusError):
    return cls(text, response=httpx.Response(status, request=REQUEST), body=None)


class FakeOpenAI:
    """Faz de openai.OpenAI: cada chave tem uma fila de respostas (ou erros a lançar)."""
    script: dict[str, list] = {}
    created: list[dict] = []

    def __init__(self, api_key, base_url=None, **options):
        FakeOpenAI.created.append({"api_key": api_key, "base_url": base_url, **options})
        self.api_key = api_key
        self.chat = self
        self.completions = self
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = FakeOpenAI.script[self.api_key].pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


@pytest.fixture
def fake():
    FakeOpenAI.script, FakeOpenAI.created = {}, []
    return FakeOpenAI


def make(keys, clock=None):
    return FallbackClient(keys, base_url="https://llm.test/v1", factory=FakeOpenAI, clock=clock or Clock())


def test_uses_the_primary_key_when_it_works(fake):
    fake.script = {"main": ["ok"], "backup": []}
    client = make(["main", "backup"])
    assert client.chat.completions.create(model="m", messages=[]) == "ok"
    assert client._clients[1].calls == []


def test_switches_to_the_fallback_when_the_quota_runs_out(fake):
    fake.script = {"main": [quota_error()], "backup": ["from backup"]}
    client = make(["main", "backup"])
    assert client.chat.completions.create(model="m", messages=[{"role": "user", "content": "q"}]) == "from backup"
    assert client._clients[1].calls == [{"model": "m", "messages": [{"role": "user", "content": "q"}]}]


def test_streaming_requests_also_fall_back(fake):
    stream = iter(["pedaço 1", "pedaço 2"])
    fake.script = {"main": [quota_error()], "backup": [stream]}
    client = make(["main", "backup"])
    assert client.chat.completions.create(model="m", messages=[], stream=True) is stream
    assert client._clients[1].calls[0]["stream"] is True


def test_exhausted_key_is_skipped_until_the_provider_wait_is_over(fake):
    clock = Clock()
    fake.script = {"main": [quota_error(), "main again"], "backup": ["b1", "b2"]}
    client = make(["main", "backup"], clock)
    assert client.chat.completions.create() == "b1"
    assert client.chat.completions.create() == "b2"                  # não gasta um pedido falhado na principal
    assert len(client._clients[0].calls) == 1
    clock.now += 14 * 60 + 57                                         # "try again in 14m56.8s"
    assert client.chat.completions.create() == "main again"          # volta à principal


def test_raises_the_quota_error_when_both_keys_are_exhausted(fake):
    fake.script = {"main": [quota_error()], "backup": [quota_error("backup TPD exhausted")]}
    with pytest.raises(RateLimitError, match="backup"):
        make(["main", "backup"]).chat.completions.create()


def test_blocked_keys_are_still_tried_as_a_last_resort(fake):
    clock = Clock()
    fake.script = {"main": [quota_error(), "main recovered early"], "backup": [quota_error()]}
    client = make(["main", "backup"], clock)
    with pytest.raises(RateLimitError):
        client.chat.completions.create()
    assert client.chat.completions.create() == "main recovered early"


def test_other_errors_do_not_use_the_fallback(fake):
    fake.script = {"main": [status_error(401, "invalid api key", AuthenticationError)], "backup": ["never"]}
    client = make(["main", "backup"])
    with pytest.raises(AuthenticationError):
        client.chat.completions.create()
    assert client._clients[1].calls == []


def test_single_key_keeps_the_sdk_retries_and_works_without_fallback(fake):
    fake.script = {"main": ["ok"]}
    client = make(["main", ""])
    assert client.keys == 1 and client.chat.completions.create() == "ok"
    assert "max_retries" not in fake.created[0]


def test_primary_has_no_sdk_retries_when_there_is_a_fallback(fake):
    make(["main", "backup"])
    assert fake.created[0]["max_retries"] == 0 and "max_retries" not in fake.created[1]


def test_same_key_twice_is_one_key(fake):
    assert make(["main", " main "]).keys == 1


def test_missing_key_is_a_clear_error(fake):
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        make(["", None])


def test_reads_both_keys_from_the_environment(fake, monkeypatch):
    monkeypatch.setattr(llm, "OpenAI", FakeOpenAI)
    monkeypatch.setenv("GROQ_API_KEY", "env-main")
    monkeypatch.setenv("GROQ_API_KEY_FALLBACK", "env-backup")
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.test/v1")
    assert llm.llm_client().keys == 2
    assert [(c["api_key"], c["base_url"]) for c in fake.created] == [("env-main", "https://llm.test/v1"),
                                                                     ("env-backup", "https://llm.test/v1")]


def test_fallback_key_is_optional(fake, monkeypatch):
    monkeypatch.setattr(llm, "OpenAI", FakeOpenAI)
    monkeypatch.setenv("GROQ_API_KEY", "env-main")
    monkeypatch.delenv("GROQ_API_KEY_FALLBACK", raising=False)
    assert llm.llm_client().keys == 1


def test_keys_never_appear_in_the_log(fake, caplog):
    fake.script = {"main-secret-123": [quota_error()], "backup-secret-456": ["ok"]}
    with caplog.at_level("WARNING", logger="multistore"):
        make(["main-secret-123", "backup-secret-456"]).chat.completions.create()
    assert "chave principal" in caplog.text
    assert "secret" not in caplog.text


@pytest.mark.parametrize("error,expected", [
    (quota_error(), True),
    (status_error(429, "Too Many Requests"), True),
    (status_error(403, "You exceeded your current quota"), True),
    (status_error(500, "internal error"), False),
    (ValueError("tokens per day"), False),
])
def test_is_quota_error(error, expected):
    assert is_quota_error(error) is expected


@pytest.mark.parametrize("text,seconds", [
    ("Please try again in 14m56.8s.", 14 * 60 + 56.8),
    ("Please try again in 1h2m3s", 3723),
    ("Please try again in 1.5s", MIN_COOLDOWN),       # pouco tempo: fica o mínimo
    ("no hint here", MIN_COOLDOWN),
])
def test_retry_after(text, seconds):
    assert retry_after(quota_error(text)) == pytest.approx(seconds)
