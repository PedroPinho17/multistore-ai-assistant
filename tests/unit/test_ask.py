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

    def __init__(self, monkeypatch, intent=None, sqls=("SELECT 1",), rows=((1,),), db_error_on=(), results=None):
        """``results``: linhas de cada ``run_query``, por ordem (senão, sempre ``rows``)."""
        self.calls = {"generate": [], "failed": [], "run": [], "chat": 0, "answer": 0}
        self._results = list(results) if results is not None else None
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

    def _generate(self, prompt, history=None, failed=None):
        self.calls["generate"].append((prompt, history))
        self.calls["failed"].append(failed)
        return self._sqls.pop(0)

    def _run(self, sql, user):
        self.calls["run"].append((sql, user))
        if len(self.calls["run"]) in self.db_error_on:
            raise psycopg.errors.UndefinedColumn('column "x" does not exist')
        return ["v"], list(self._results.pop(0)) if self._results is not None else self.rows

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
    assert fake.calls["generate"][1][0] == "quantas vendas?"          # a pergunta original (RAG certo)
    failed_sql, error = fake.calls["failed"][1]
    assert failed_sql == "DELETE FROM sales" and "SELECT" in error   # o motivo do validador


def test_retries_once_after_database_error_with_the_error_and_the_sql(monkeypatch, caplog):
    fake = Fake(monkeypatch, intent="data", sqls=["SELECT x FROM sales", "SELECT total FROM sales"],
                db_error_on={1})
    with caplog.at_level("WARNING", logger="multistore"):
        result = ask("vendas?", LOJA, "pt", HISTORY)
    assert result["kind"] == "sql" and result["sql"] == "SELECT total FROM sales"
    assert fake.calls["failed"] == [None, ("SELECT x FROM sales", 'column "x" does not exist')]
    assert fake.calls["generate"][1] == ("vendas?", HISTORY)          # o histórico continua lá
    assert [r for r in caplog.records if "a pedir uma correção" in r.getMessage()
            and "UndefinedColumn" in r.getMessage() and "SELECT x FROM sales" in r.getMessage()]


def test_the_correction_is_validated_again_before_running(monkeypatch):
    fake = Fake(monkeypatch, intent="data", sqls=["SELECT x FROM sales", "DELETE FROM sales"], db_error_on={1})
    assert ask("q", LOJA)["kind"] == "error"
    assert [sql for sql, _ in fake.calls["run"]] == ["SELECT x FROM sales"]   # a correção nunca correu


def test_only_one_correction_even_if_it_fails_again(monkeypatch, caplog):
    fake = Fake(monkeypatch, intent="data", sqls=["SELECT x FROM sales", "SELECT y FROM sales"],
                db_error_on={1, 2})
    with caplog.at_level("WARNING", logger="multistore"):
        result = ask("q", LOJA, "en")
    assert result == {"sql": None, "kind": "error", "error": ERROR_MESSAGES["en"]}
    assert len(fake.calls["generate"]) == 2 and len(fake.calls["run"]) == 2
    assert any("depois da correção" in r.getMessage() for r in caplog.records)


def test_the_correction_can_still_route_to_no_sql(monkeypatch):
    fake = Fake(monkeypatch, intent="data", sqls=["SELECT x FROM sales", "NO_SQL"], db_error_on={1})
    assert ask("q", LOJA, "es")["answer"] == "chat[es]"
    assert len(fake.calls["run"]) == 1


# ---------- 0 linhas com ILIKE sem %: alarga uma vez, sem LLM ----------

NARROW = "SELECT name FROM stores WHERE name ILIKE 'Maia'"
WIDE = "SELECT name FROM stores WHERE name ILIKE '%Maia%'"


def test_empty_ilike_filter_is_widened_once_without_the_llm(monkeypatch):
    fake = Fake(monkeypatch, intent="data", sqls=[NARROW], results=[[], [("BurgerLab Maia",)]])
    result = ask("loja Maia?", LOJA)
    assert [sql for sql, _ in fake.calls["run"]] == [NARROW, WIDE]
    assert result["sql"] == WIDE and result["rows"] == [("BurgerLab Maia",)]   # o SQL mostrado é o que correu
    assert len(fake.calls["generate"]) == 1


def test_an_all_null_aggregate_also_counts_as_no_data(monkeypatch):
    narrow = "SELECT SUM(total) FROM sales AS v JOIN stores AS s ON s.id = v.store_id WHERE s.name ILIKE 'maia'"
    fake = Fake(monkeypatch, intent="data", sqls=[narrow], results=[[(None,)], [(1234.5,)]])
    assert ask("faturação da Maia?", LOJA)["rows"] == [(1234.5,)]
    assert "'%maia%'" in fake.calls["run"][1][0]


def test_if_the_wider_query_finds_nothing_the_original_stays(monkeypatch):
    fake = Fake(monkeypatch, intent="data", sqls=[NARROW], results=[[], []])
    result = ask("q", LOJA)
    assert result["sql"] == NARROW and result["rows"] == [] and len(fake.calls["run"]) == 2


def test_if_the_wider_query_fails_the_original_stays_and_the_llm_is_not_called(monkeypatch):
    fake = Fake(monkeypatch, intent="data", sqls=[NARROW], results=[[]], db_error_on={2})
    result = ask("q", LOJA)
    assert result["kind"] == "sql" and result["sql"] == NARROW
    assert len(fake.calls["generate"]) == 1


@pytest.mark.parametrize("sql", [
    WIDE,                                                            # já tem %
    "SELECT name FROM stores WHERE name NOT ILIKE 'Maia'",          # alargar daria menos linhas
    "SELECT name FROM stores WHERE name = 'Maia'",                   # não é ILIKE
])
def test_no_second_query_when_there_is_nothing_to_widen(monkeypatch, sql):
    fake = Fake(monkeypatch, intent="data", sqls=[sql], results=[[]])
    assert ask("q", LOJA)["rows"] == []
    assert len(fake.calls["run"]) == 1


def test_results_with_data_are_never_widened(monkeypatch):
    fake = Fake(monkeypatch, intent="data", sqls=[NARROW], results=[[("Maia",)]])
    ask("q", LOJA)
    assert len(fake.calls["run"]) == 1


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
