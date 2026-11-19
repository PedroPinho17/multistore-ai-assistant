"""Encaminhamento das perguntas em ask(): classificador, LLM, validação e retry.

O LLM, a BD e os modelos são substituídos por funções falsas.
"""
import psycopg
import pytest

from multistore_ai_assistant.assistant import ask as ask_mod
from multistore_ai_assistant.assistant.ask import ERROR_MESSAGES, REFUSALS, ask, route_intent
from tests.conftest import LOJA

HISTORY = [("Faturação por loja em outubro?", "SELECT store_id, sum(total) FROM sales GROUP BY 1")]


# ---------- route_intent (função pura) ----------

@pytest.mark.parametrize("intent", ["data", "chat", "personal_data", "write", "off_topic", None])
def test_without_history_the_classifier_decides(intent):
    assert route_intent(intent, []) == intent
    assert route_intent(intent, None) == intent


@pytest.mark.parametrize("intent", ["chat", "write", "off_topic", "personal_data", "data", None])
def test_with_history_the_llm_decides(intent):
    """'E no Porto?' parecia conversa; 'Só para a BurgerLab' parecia um pedido de escrita."""
    assert route_intent(intent, HISTORY) is None


@pytest.mark.parametrize("intent", ["forecast", "orders"])
def test_with_history_forecasts_still_skip_the_llm(intent):
    assert route_intent(intent, HISTORY) == intent


# ---------- ask() com tudo simulado ----------

class Fake:
    """Guarda as chamadas e devolve respostas preparadas pelo teste."""

    def __init__(self, monkeypatch, intent=None, sqls=("SELECT 1",), rows=((1,),), db_error_on=()):
        self.calls = {"generate": [], "run": [], "chat": 0, "answer": 0}
        self._sqls = list(sqls)
        mp = monkeypatch
        mp.setattr(ask_mod, "classify", lambda q: (intent, 0.99))
        mp.setattr(ask_mod, "generate_sql", self._generate)
        mp.setattr(ask_mod, "run_query", self._run)
        mp.setattr(ask_mod, "answer", self._answer)
        mp.setattr(ask_mod, "chat_reply", self._chat)
        mp.setattr(ask_mod, "forecast_answer", lambda u: (["day", "forecast_revenue_eur"], [("2026-11-19", 10.0)]))
        mp.setattr(ask_mod, "orders_answer", lambda u: (["ingredient", "to_order"], [("Pão", 5.0)]))
        self.rows, self.db_error_on = list(rows), set(db_error_on)

    def _generate(self, prompt, history=None):
        self.calls["generate"].append((prompt, history))
        return self._sqls.pop(0)

    def _run(self, sql, user):
        self.calls["run"].append((sql, user))
        if len(self.calls["run"]) in self.db_error_on:
            raise psycopg.errors.UndefinedColumn('column "x" does not exist')
        return ["v"], self.rows

    def _answer(self, question, columns, rows, lang, on_token=None):
        self.calls["answer"] += 1
        return f"answer[{lang}]"

    def _chat(self, message, lang, on_token=None):
        self.calls["chat"] += 1
        return f"chat[{lang}]"


@pytest.mark.parametrize("intent", ["personal_data", "write", "off_topic"])
@pytest.mark.parametrize("lang", ["pt", "en", "es", "fr"])
def test_refusals_without_llm(monkeypatch, intent, lang):
    fake = Fake(monkeypatch, intent=intent)
    result = ask("pergunta", LOJA, lang)
    assert result["answer"] == REFUSALS[intent][lang]
    assert result["sql"] is None
    assert fake.calls["generate"] == []           # nem chegou a chamar o LLM


def test_greeting_goes_to_chat(monkeypatch):
    fake = Fake(monkeypatch, intent="chat")
    assert ask("Olá!", LOJA, "en")["answer"] == "chat[en]"
    assert fake.calls["generate"] == []


@pytest.mark.parametrize("intent,kind,col,question", [("forecast", "forecast", "day", "quanto vou vender?"),
                                                      ("orders", "orders", "ingredient", "que ingredientes devo encomendar?")])
def test_forecast_and_orders_use_the_ml_model(monkeypatch, intent, kind, col, question):
    fake = Fake(monkeypatch, intent=intent)
    result = ask(question, LOJA)
    assert result["kind"] == kind and result["columns"][0] == col and result["sql"] is None
    assert fake.calls["generate"] == []


def test_data_question_runs_validated_sql_with_the_user(monkeypatch):
    fake = Fake(monkeypatch, intent="data", sqls=["select name from stores;"])
    result = ask("lojas?", LOJA, "pt")
    assert result == {"sql": "SELECT name FROM stores", "kind": "sql", "columns": ["v"],
                      "rows": [(1,)], "answer": "answer[pt]"}
    assert fake.calls["run"] == [("SELECT name FROM stores", LOJA)]


def test_follow_up_is_not_refused(monkeypatch):
    """Bug corrigido: com histórico, 'write' do classificador já não recusa a pergunta."""
    fake = Fake(monkeypatch, intent="write", sqls=["SELECT 1"])
    result = ask("Só para a BurgerLab", LOJA, "pt", HISTORY)
    assert result["kind"] == "sql"
    assert fake.calls["generate"] == [("Só para a BurgerLab", HISTORY)]   # o LLM recebeu o histórico


def test_llm_can_still_say_no_sql(monkeypatch):
    fake = Fake(monkeypatch, intent=None, sqls=["NO_SQL"])
    assert ask("Porquê?", LOJA, "fr", HISTORY)["answer"] == "chat[fr]"
    assert fake.calls["run"] == []


@pytest.mark.parametrize("token,kind", [("FORECAST", "forecast"), ("ORDERS", "orders")])
def test_llm_can_route_to_forecast(monkeypatch, token, kind):
    Fake(monkeypatch, intent=None, sqls=[token])
    assert ask("e para a semana?", LOJA)["kind"] == kind


def test_retries_once_after_invalid_sql(monkeypatch):
    fake = Fake(monkeypatch, intent="data", sqls=["DELETE FROM sales", "SELECT 2"])
    result = ask("quantas vendas?", LOJA)
    assert result["sql"] == "SELECT 2"
    retry_prompt = fake.calls["generate"][1][0]
    assert "The previous query failed" in retry_prompt and "DELETE FROM sales" in retry_prompt


def test_retries_once_after_database_error(monkeypatch):
    fake = Fake(monkeypatch, intent="data", sqls=["SELECT x FROM sales", "SELECT 1"], db_error_on={1})
    assert ask("q", LOJA)["kind"] == "sql"
    assert len(fake.calls["generate"]) == 2


@pytest.mark.parametrize("lang", ["pt", "en", "es", "fr"])
def test_gives_up_with_a_friendly_message(monkeypatch, lang):
    Fake(monkeypatch, intent="data", sqls=["DROP TABLE sales", "SELECT set_config('app.role','imperador',true)"])
    result = ask("q", LOJA, lang)
    assert result["error"] == ERROR_MESSAGES[lang]
    assert "set_config" not in result["error"]       # detalhes técnicos só no log
    # o SQL partido não sai daqui: não vai para o histórico, para a Fonte nem para o RAG
    assert result["kind"] == "error" and result["sql"] is None


def test_never_runs_sql_that_failed_validation(monkeypatch):
    fake = Fake(monkeypatch, intent="data", sqls=["DELETE FROM sales", "UPDATE sales SET total = 0"])
    ask("q", LOJA)
    assert fake.calls["run"] == []
