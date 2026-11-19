"""Funções pequenas: histórico, contexto RLS assinado, classificador e previsão."""
import hashlib
import hmac

import pandas as pd
import pytest

from multistore_ai_assistant.api.conversations import build_history
from multistore_ai_assistant.db import query
from multistore_ai_assistant.forecast import service
from multistore_ai_assistant.intent import predict
from tests.conftest import IMPERADOR, LOJA, MARCA

# ---------- histórico da conversa ----------


def test_build_history_pairs_questions_with_sql_or_label():
    rows = [
        ("user", "Vendas em outubro?", None, None),
        ("assistant", "Foram 10 €.", "SELECT 1", "sql"),
        ("user", "E para a semana?", None, None),
        ("assistant", "Vais vender 5 €.", None, "forecast"),
        ("user", "Que ingredientes compro?", None, None),
        ("assistant", "Pão.", None, "orders"),
        ("user", "Obrigado", None, None),
        ("assistant", "De nada!", None, "no_sql"),
    ]
    assert build_history(rows) == [
        ("Vendas em outubro?", "SELECT 1"),
        ("E para a semana?", "FORECAST"),
        ("Que ingredientes compro?", "ORDERS"),
        ("Obrigado", "NO_SQL"),
    ]


def test_build_history_ignores_unanswered_and_orphan_messages():
    rows = [("assistant", "resposta sem pergunta", None, None),   # cortada pelo LIMIT
            ("user", "pergunta", None, None)]                     # ainda sem resposta
    assert build_history(rows) == []


def test_build_history_skips_failed_answers():
    rows = [("user", "q1", None, None), ("assistant", "erro", None, "error"),
            ("user", "q2", None, None), ("assistant", "ok", "SELECT 2", "sql")]
    assert build_history(rows) == [("q2", "SELECT 2")]


def test_build_history_empty():
    assert build_history([]) == []


# ---------- contexto RLS assinado ----------

@pytest.fixture
def key(monkeypatch):
    monkeypatch.setattr(query, "_rls_key", lambda: "k" * 64)
    return "k" * 64


@pytest.mark.parametrize("user,expected", [
    (IMPERADOR, ("imperador", "", "")),
    (MARCA, ("marca", "1", "")),
    (LOJA, ("loja", "", "1")),
])
def test_context_values(key, user, expected):
    assert query._context(user)[:3] == expected


def test_context_signature_matches_postgres_formula(key):
    """Tem de ser igual a encode(hmac(role|brand|store, key, 'sha256'), 'hex') em db/migrations/V002__security.sql."""
    role, brand, store, sig = query._context(LOJA)
    expected = hmac.new(key.encode(), f"{role}|{brand}|{store}".encode(), hashlib.sha256).hexdigest()
    assert sig == expected and len(sig) == 64


def test_each_profile_gets_a_different_signature(key):
    sigs = {query._context(u)[3] for u in (IMPERADOR, MARCA, LOJA,
                                           {**LOJA, "store_id": 2}, {**MARCA, "brand_id": 2})}
    assert len(sigs) == 5


# ---------- classificador de intenção ----------

@pytest.mark.parametrize("text,rest", [
    ("Olá, quanto faturou Braga?", "quanto faturou Braga?"),
    ("Bom dia! Vendas de ontem", "Vendas de ontem"),
    ("hello, sales today", "sales today"),
    ("Bonjour, ventes", "ventes"),
    ("Vendas de ontem", "Vendas de ontem"),
    ("Olá!", ""),
])
def test_strip_greeting(text, rest):
    assert predict.strip_greeting(text) == rest


@pytest.mark.parametrize("text", ["Olá!", "Bom dia", "hi", "Hola", "Bonsoir !"])
def test_greeting_only_is_chat_without_loading_a_model(monkeypatch, text):
    monkeypatch.setattr(predict, "backend", lambda: pytest.fail("não devia carregar o modelo"))
    assert predict.classify(text) == ("chat", 1.0)


def test_no_model_means_the_llm_decides(monkeypatch):
    monkeypatch.setattr(predict, "backend", lambda: "none")
    assert predict.classify("Vendas de Gaia ontem") == (None, 0.0)


def test_backend_choice(monkeypatch, tmp_path):
    xlmr = tmp_path / "intent-xlmr"
    minilm = tmp_path / "intent.joblib"
    monkeypatch.setattr(predict, "XLMR_PATH", xlmr)
    monkeypatch.setattr(predict, "MODEL_PATH", minilm)
    monkeypatch.setenv("INTENT_MODEL", "xlmr")
    assert predict.backend() == "none"
    minilm.write_bytes(b"x")
    assert predict.backend() == "minilm"                 # XLM-R em falta -> MiniLM
    xlmr.mkdir()
    (xlmr / "model.safetensors").write_bytes(b"x")
    assert predict.backend() == "xlmr"
    monkeypatch.setenv("INTENT_MODEL", "minilm")
    assert predict.backend() == "minilm"                 # escolha explícita


def test_xlmr_path_does_not_depend_on_working_directory():
    """Bug corrigido: com um caminho relativo, arrancar noutra pasta trocava para o MiniLM."""
    assert predict.XLMR_PATH.is_absolute()
    assert predict.XLMR_PATH.parent.name == "models"


# ---------- previsão filtrada pelas lojas visíveis ----------

@pytest.fixture
def fake_forecast(monkeypatch):
    days = pd.to_datetime(["2026-11-19", "2026-11-19", "2026-11-20", "2026-11-20"])
    monkeypatch.setattr(service, "forecast", lambda d: pd.DataFrame(
        {"store_id": [1, 2, 1, 2], "day": days, "revenue": [100.0, 50.0, 110.0, 60.0]}))
    monkeypatch.setattr(service, "suggest_orders", lambda s, d: pd.DataFrame({
        "store_id": [1, 2, 1], "ingredient": ["Pão", "Pão", "Carne"], "unit": ["un", "un", "kg"],
        "needed": [10.0, 99.0, 4.0], "stock": [2.0, 0.0, 1.0], "to_order": [8.0, 99.0, 3.0]}))


def test_forecast_only_sums_visible_stores(monkeypatch, fake_forecast):
    monkeypatch.setattr(service, "visible_stores", lambda u: [1])
    columns, rows = service.forecast_answer(LOJA)
    assert columns == ["day", "forecast_revenue_eur"]
    assert rows == [("2026-11-19", 100.0), ("2026-11-20", 110.0)]


def test_forecast_for_the_whole_group(monkeypatch, fake_forecast):
    monkeypatch.setattr(service, "visible_stores", lambda u: [1, 2])
    assert service.forecast_answer(IMPERADOR)[1] == [("2026-11-19", 150.0), ("2026-11-20", 170.0)]


def test_orders_only_for_visible_stores_sorted(monkeypatch, fake_forecast):
    monkeypatch.setattr(service, "visible_stores", lambda u: [1])
    columns, rows = service.orders_answer(LOJA)
    assert columns == ["ingredient", "unit", "needed_7_days", "stock", "to_order"]
    assert rows == [("Pão", "un", 10.0, 2.0, 8.0), ("Carne", "kg", 4.0, 1.0, 3.0)]


def test_no_visible_stores_means_no_forecast(monkeypatch, fake_forecast):
    monkeypatch.setattr(service, "visible_stores", lambda u: [])
    assert service.forecast_answer({"role": "x", "brand_id": None, "store_id": None})[1] == []
