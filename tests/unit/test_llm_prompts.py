"""Construção das mensagens enviadas ao LLM (sem chamar o LLM)."""
from types import SimpleNamespace

import pytest

from multistore_ai_assistant.assistant import answer as answer_mod
from multistore_ai_assistant.assistant import sql_generator


class FakeClient:
    def __init__(self, reply: str):
        self.reply = reply
        self.sent = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.sent.append(kwargs)
        msg = SimpleNamespace(content=self.reply)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


@pytest.fixture
def llm(monkeypatch):
    def install(reply="ok", module=sql_generator):
        client = FakeClient(reply)
        monkeypatch.setattr(module, "client", client)
        return client
    monkeypatch.setattr(sql_generator, "get_schema_text", lambda: "stores(id integer, name text)")
    monkeypatch.setattr(sql_generator, "find_similar", lambda q: [("Lojas?", "SELECT name FROM stores")])
    return install


# ---------- generate_sql ----------

@pytest.mark.parametrize("reply,expected", [
    ("SELECT 1", "SELECT 1"),
    ("```sql\nSELECT 1;\n```", "SELECT 1"),
    ("```\nSELECT 1\n```", "SELECT 1"),
    ("  FORECAST  ", "FORECAST"),
])
def test_generate_sql_cleans_the_reply(llm, reply, expected):
    llm(reply)
    assert sql_generator.generate_sql("q") == expected


def test_generate_sql_prompt_has_schema_examples_and_date(llm):
    client = llm()
    sql_generator.generate_sql("Quantas lojas?")
    system = client.sent[0]["messages"][0]["content"]
    assert "stores(id integer, name text)" in system
    assert "Q: Lojas?\nSQL: SELECT name FROM stores" in system
    assert "Today's date is" in system
    assert client.sent[0]["temperature"] == 0


def test_generate_sql_sends_history_as_turns(llm):
    client = llm()
    sql_generator.generate_sql("E no Porto?", [("Vendas em outubro?", "SELECT 1"), ("E em setembro?", "SELECT 2")])
    roles = [(m["role"], m["content"]) for m in client.sent[0]["messages"][1:]]
    assert roles == [("user", "Vendas em outubro?"), ("assistant", "SELECT 1"),
                     ("user", "E em setembro?"), ("assistant", "SELECT 2"),
                     ("user", "E no Porto?")]


def test_correction_sends_the_failed_sql_and_the_error_as_turns(llm, monkeypatch):
    client = llm("SELECT total FROM sales")
    searched = []
    monkeypatch.setattr(sql_generator, "find_similar", lambda q: searched.append(q) or [])
    history = [("Vendas em outubro?", "SELECT 1")]
    sql_generator.generate_sql("E em setembro?", history,
                               failed=("SELECT x FROM sales", 'column "x" does not exist'))
    sent = client.sent[0]
    roles = [(m["role"], m["content"]) for m in sent["messages"][1:]]
    assert roles[:4] == [("user", "Vendas em outubro?"), ("assistant", "SELECT 1"),
                         ("user", "E em setembro?"), ("assistant", "SELECT x FROM sales")]
    assert roles[4][0] == "user" and 'column "x" does not exist' in roles[4][1]
    assert searched == ["E em setembro?"]                     # RAG pela pergunta, não pelo erro
    assert sent["temperature"] == 0                            # a correção também é determinística


def test_correction_error_is_truncated(llm):
    client = llm()
    sql_generator.generate_sql("q", failed=("SELECT 1", "x" * 5000))
    fix = client.sent[0]["messages"][-1]["content"]
    assert "x" * sql_generator.MAX_ERROR_CHARS in fix and "x" * (sql_generator.MAX_ERROR_CHARS + 1) not in fix


def test_without_a_failure_there_is_no_correction_turn(llm):
    client = llm()
    sql_generator.generate_sql("q")
    assert [m["role"] for m in client.sent[0]["messages"]] == ["system", "user"]


def test_prompt_asks_for_ilike_with_wildcards_and_shows_an_example(llm):
    client = llm()
    sql_generator.generate_sql("q")
    system = client.sent[0]["messages"][0]["content"]
    assert "ILIKE with % on both sides" in system
    assert "st.name ILIKE '%Coimbra%' AND i.name ILIKE '%cheddar%'" in system


# ---------- answer / chat_reply ----------

@pytest.mark.parametrize("lang,name", [("pt", "European Portuguese"), ("en", "English"),
                                       ("es", "Spanish"), ("fr", "French")])
def test_answer_uses_the_site_language(llm, lang, name):
    client = llm("Resposta.", module=answer_mod)
    assert answer_mod.answer("q", ["a"], [(1,)], lang) == "Resposta."
    assert name in client.sent[0]["messages"][0]["content"]


def test_answer_limits_rows_sent_to_the_llm(llm):
    client = llm(module=answer_mod)
    rows = [(i,) for i in range(120)]
    answer_mod.answer("q", ["n"], rows, "pt")
    user_msg = client.sent[0]["messages"][1]["content"]
    assert "\n49" in user_msg and "\n50\n" not in user_msg
    assert "(+70 more rows)" in user_msg


def test_answer_handles_empty_llm_reply(llm):
    llm(None, module=answer_mod)
    assert answer_mod.answer("q", ["a"], [], "pt") == ""


def test_chat_reply_is_told_it_has_no_data(llm):
    client = llm(" Olá! ", module=answer_mod)
    assert answer_mod.chat_reply("Olá", "pt") == "Olá!"
    assert "NO access to any data" in client.sent[0]["messages"][0]["content"]
