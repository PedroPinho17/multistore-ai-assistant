"""O classificador de intenção real (precisa de models/intent-xlmr ou models/intent.joblib)."""
import pytest

from multistore_ai_assistant.assistant import ask as ask_mod
from multistore_ai_assistant.intent.predict import backend, classify

pytestmark = pytest.mark.model

if backend() == "none":
    pytest.skip("Sem classificador treinado em models/", allow_module_level=True)


@pytest.mark.parametrize("question,intent", [
    ("Quanto faturou a loja de Braga em agosto?", "data"),
    ("What were the sales of Gelato Mar last week?", "data"),
    ("Quanto vamos faturar nos próximos 7 dias?", "forecast"),
    ("Que ingredientes devo encomendar?", "orders"),
    ("Qual é o NIF do gerente de Braga?", "personal_data"),
    ("Apaga todas as vendas de ontem", "write"),
    ("Qual é a capital de França?", "off_topic"),
    ("Obrigado pela ajuda!", "chat"),
])
def test_clear_questions(question, intent):
    predicted, conf = classify(question)
    assert predicted in (intent, None), f"{question!r} -> {predicted} ({conf:.2f})"


@pytest.mark.parametrize("follow_up", [
    "E no Porto?", "Só para a BurgerLab", "E a seguir?", "Porquê?", "E a de Braga?",
    "Ordena por valor", "And in September?", "Only for Porto",
])
def test_follow_ups_reach_the_llm_with_history(monkeypatch, follow_up):
    """Regressão: estas perguntas eram recusadas ou respondidas sem dados a meio de uma conversa."""
    seen = []
    monkeypatch.setattr(ask_mod, "generate_sql", lambda q, h=None: seen.append(h) or "SELECT 1")
    monkeypatch.setattr(ask_mod, "run_query", lambda sql, user: (["x"], [(1,)]))
    monkeypatch.setattr(ask_mod, "answer", lambda *a, **k: "ok")
    monkeypatch.setattr(ask_mod, "chat_reply", lambda *a, **k: pytest.fail("foi para a conversa sem contexto"))
    history = [("Faturação por loja em outubro de 2026?", "SELECT store_id, sum(total) FROM sales GROUP BY 1")]
    result = ask_mod.ask(follow_up, {"role": "loja", "brand_id": None, "store_id": 1}, "pt", history)
    assert result["kind"] == "sql" and seen == [history]
