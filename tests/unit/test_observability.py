"""Trace de cada pergunta (tokens, intenção, tentativas) e módulos no ask()."""
from types import SimpleNamespace

import psycopg
import pytest

from multistore_ai_assistant import observability as obs
from multistore_ai_assistant.assistant import ask as ask_mod
from tests.conftest import LOJA


def response(prompt=100, completion=20):
    return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion))


# ---------- Trace ----------

def test_outside_a_request_nothing_is_recorded():
    obs.record_llm(response())
    obs.record_sql_attempt(RuntimeError("x"))
    assert obs.current() is None


def test_tokens_are_summed_across_llm_calls():
    with obs.trace() as t:
        obs.record_llm(response(100, 20))
        obs.record_llm(response(50, 5))
    assert (t.llm_calls, t.prompt_tokens, t.completion_tokens) == (2, 150, 25)


def test_responses_without_usage_still_count_the_call():
    with obs.trace() as t:
        obs.record_llm(SimpleNamespace())
    assert (t.llm_calls, t.prompt_tokens) == (1, 0)


def test_sql_attempts_and_failures():
    with obs.trace() as t:
        obs.record_sql_attempt(psycopg.errors.UndefinedColumn("coluna x"))
        obs.record_sql_attempt()
    assert t.sql_attempts == 2 and t.sql_failed and "UndefinedColumn" in t.error


def test_error_text_is_truncated():
    with obs.trace() as t:
        obs.record_sql_attempt(RuntimeError("x" * 2000))
    assert len(t.error) == 500


def test_intent_and_confidence():
    with obs.trace() as t:
        obs.record_intent("forecast", 0.98765)
    assert (t.intent, t.confidence) == ("forecast", 0.9877)


def test_traces_do_not_leak_between_requests():
    with obs.trace() as first:
        obs.record_llm(response())
    with obs.trace() as second:
        pass
    assert first.llm_calls == 1 and second.llm_calls == 0 and obs.current() is None


def test_duration_is_measured():
    with obs.trace() as t:
        pass
    assert 0 <= t.duration_ms() < 1000


def test_llm_wrappers_record_usage(monkeypatch):
    from multistore_ai_assistant.assistant import answer as answer_mod
    from multistore_ai_assistant.assistant import sql_generator as gen

    fake = SimpleNamespace(**response().__dict__, choices=[SimpleNamespace(message=SimpleNamespace(content="SELECT 1"))])
    create = lambda **kw: fake  # noqa: E731
    monkeypatch.setattr(gen.client.chat.completions, "create", create)
    monkeypatch.setattr(gen, "find_similar", lambda q: [])
    monkeypatch.setattr(gen, "get_schema_text", lambda: "sales(id int)")
    with obs.trace() as t:
        gen.generate_sql("q")
        answer_mod.answer("q", ["x"], [(1,)], "pt")
        answer_mod.chat_reply("olá", "pt")
    assert (t.llm_calls, t.prompt_tokens, t.completion_tokens) == (3, 300, 60)


# ---------- módulos no ask() ----------

@pytest.fixture
def fake_pipeline(monkeypatch):
    calls = {"generate": 0, "run": 0, "forecast": 0}
    monkeypatch.setattr(ask_mod, "answer", lambda *a, **k: "ok")
    monkeypatch.setattr(ask_mod, "chat_reply", lambda *a, **k: "olá")
    monkeypatch.setattr(ask_mod, "run_query", lambda s, u: calls.__setitem__("run", calls["run"] + 1) or (["x"], [(1,)]))
    monkeypatch.setattr(ask_mod, "forecast_answer",
                        lambda u: calls.__setitem__("forecast", calls["forecast"] + 1) or (["day"], [("d",)]))

    def setup(intent, sql="SELECT 1"):
        monkeypatch.setattr(ask_mod, "classify", lambda q: (intent, 0.9))

        def gen(q, h=None):
            calls["generate"] += 1
            return sql
        monkeypatch.setattr(ask_mod, "generate_sql", gen)
        return calls
    return setup


def test_forecast_without_the_module_is_denied_before_touching_the_model(fake_pipeline):
    calls = fake_pipeline("forecast")
    result = ask_mod.ask("Quanto vou vender?", {**LOJA, "modules": ["sql"]}, "pt")
    assert result["kind"] == "denied" and result["module"] == "forecast"
    assert "previsão de vendas" in result["answer"] and calls["forecast"] == 0


def test_sql_without_the_module_is_denied_before_running(fake_pipeline):
    calls = fake_pipeline(None)
    result = ask_mod.ask("Faturação?", {**LOJA, "modules": ["forecast"]}, "en")
    assert result["kind"] == "denied" and "data questions" in result["answer"] and calls["run"] == 0


def test_llm_routing_to_forecast_also_checks_the_module(fake_pipeline):
    fake_pipeline(None, sql="FORECAST")
    assert ask_mod.ask("q", {**LOJA, "modules": ["sql"]}, "pt")["kind"] == "denied"


def test_chat_and_refusals_need_no_module(fake_pipeline):
    fake_pipeline("chat")
    assert ask_mod.ask("Olá", {**LOJA, "modules": ["forecast"]}, "pt")["kind"] == "no_sql"


@pytest.mark.parametrize("lang,word", [("pt", "módulo"), ("en", "module"), ("es", "módulo"), ("fr", "module")])
def test_denial_message_is_translated(lang, word):
    assert word in ask_mod.denied("orders", lang)["answer"]


def test_ask_records_intent_and_attempts(fake_pipeline):
    fake_pipeline("data")
    with obs.trace() as t:
        ask_mod.ask("Faturação?", LOJA, "pt")
    assert (t.intent, t.sql_attempts, t.sql_failed) == ("data", 1, False)


def test_a_retried_query_is_marked_as_failed_once(monkeypatch, fake_pipeline):
    fake_pipeline("data")
    runs = iter([psycopg.errors.UndefinedColumn("x"), None])

    def run(sql, user):
        err = next(runs)
        if err:
            raise err
        return ["x"], [(1,)]
    monkeypatch.setattr(ask_mod, "run_query", run)
    with obs.trace() as t:
        result = ask_mod.ask("Faturação?", LOJA, "pt")
    assert result["kind"] == "sql" and t.sql_attempts == 2 and t.sql_failed
