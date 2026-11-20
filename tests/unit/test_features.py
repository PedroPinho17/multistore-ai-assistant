"""Streaming (/ask/stream), explicação do SQL (/explain), alertas (/alerts),
perguntas de seguimento, cache de SQL no ``ask`` e a chave dessa cache (BD e LLM simulados)."""
import json
from pathlib import Path

import pandas as pd
import psycopg
import pytest
from fastapi.testclient import TestClient

from multistore_ai_assistant import observability as obs
from multistore_ai_assistant.api import alerts as alerts_mod
from multistore_ai_assistant.api import auth
from multistore_ai_assistant.api import main as api
from multistore_ai_assistant.assistant import ask as ask_mod
from multistore_ai_assistant.assistant.question_key import question_key
from multistore_ai_assistant.assistant.suggest import suggestions
from tests.conftest import IMPERADOR, LOJA, patch_route

client = TestClient(api.app)


def bearer(user=LOJA) -> dict:
    return {"Authorization": "Bearer " + auth.create_token(user)}


def sse_events(response) -> list[dict]:
    return [json.loads(chunk[len("data: "):]) for chunk in response.text.split("\n\n") if chunk.startswith("data: ")]


@pytest.fixture
def conversation(monkeypatch):
    saved = []
    patch_route(monkeypatch, "owns", lambda u, c: c == 7)
    patch_route(monkeypatch, "create_conversation", lambda u, q: 99)
    patch_route(monkeypatch, "get_history", lambda c: [])
    patch_route(monkeypatch, "add_message", lambda *a, **k: saved.append(a))
    return saved


# ---------- /ask/stream ----------

def streaming_ask(question, user, lang, history, on_event=None):
    on_event({"type": "status", "step": "classify"})
    on_event({"type": "status", "step": "query"})
    on_event({"type": "data", "kind": "sql", "sql": "SELECT 1", "columns": ["marca"], "rows": [["A"], ["B"]]})
    for piece in ("Duas ", "marcas."):
        on_event({"type": "token", "text": piece})
    return {"sql": "SELECT 1", "kind": "sql", "columns": ["marca"], "rows": [["A"], ["B"]], "answer": "Duas marcas."}


def test_stream_sends_status_data_tokens_and_done(monkeypatch, conversation):
    patch_route(monkeypatch, "ask", streaming_ask)
    r = client.post("/ask/stream", json={"question": "Marcas?", "lang": "pt"}, headers=bearer())
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = sse_events(r)
    assert [e["type"] for e in events] == ["status", "status", "data", "token", "token", "done"]
    done = events[-1]
    assert "".join(e["text"] for e in events if e["type"] == "token") == done["answer"] == "Duas marcas."
    assert done["conversation_id"] == 99 and "request_id" in done
    assert done["suggestions"][0] == "Mostra a evolução por mês"        # loja: sem "E por loja?"
    assert len(conversation) == 2                    # pergunta + resposta gravadas, como no /ask


def test_stream_turns_failures_into_an_error_event(monkeypatch, conversation):
    def boom(*a, **k):
        raise RuntimeError("password=segredo")
    patch_route(monkeypatch, "ask", boom)
    r = client.post("/ask/stream", json={"question": "q", "lang": "en"}, headers=bearer())
    events = sse_events(r)
    assert events[-1]["type"] == "error" and events[-1]["code"] == "unavailable"
    assert "segredo" not in r.text and conversation == []


def test_stream_checks_the_conversation_before_streaming(conversation):
    r = client.post("/ask/stream", json={"question": "q", "conversation_id": 8}, headers=bearer())
    assert r.status_code == 404 and r.json()["detail"]["code"] == "conv_not_found"


def test_stream_requires_login():
    assert client.post("/ask/stream", json={"question": "q"}).status_code in (401, 403)


def test_ask_json_also_returns_suggestions(monkeypatch, conversation):
    patch_route(monkeypatch, "ask", lambda *a, **k: {"sql": None, "kind": "forecast", "columns": ["d"],
                                                      "rows": [["x"]], "answer": "ok"})
    body = client.post("/ask", json={"question": "Previsão?", "lang": "en"}, headers=bearer()).json()
    assert body["suggestions"][0] == "Which ingredients should I order?"


# ---------- /explain ----------

def test_explain_only_for_own_answers(monkeypatch):
    asked = []
    patch_route(monkeypatch, "sql_of_request", lambda u, rid: "SELECT 1" if (u, rid) == (LOJA["username"], 5) else None)
    patch_route(monkeypatch, "explain_sql", lambda sql, lang: asked.append((sql, lang)) or "Conta as vendas.")
    ok = client.post("/explain", json={"request_id": 5, "lang": "fr"}, headers=bearer())
    assert ok.status_code == 200 and ok.json() == {"explanation": "Conta as vendas."} and asked == [("SELECT 1", "fr")]
    other = client.post("/explain", json={"request_id": 6}, headers=bearer())
    assert other.status_code == 404 and other.json()["detail"]["code"] == "answer_not_found"


def test_explain_needs_the_sql_module(monkeypatch, fake_users):
    fake_users[LOJA["username"]]["modules"] = ["forecast"]
    patch_route(monkeypatch, "sql_of_request", lambda u, rid: "SELECT 1")
    r = client.post("/explain", json={"request_id": 5}, headers=bearer())
    assert r.status_code == 403 and r.json()["detail"]["code"] == "no_module"


def test_explain_hides_llm_failures(monkeypatch):
    patch_route(monkeypatch, "sql_of_request", lambda u, rid: "SELECT 1")

    def boom(sql, lang):
        raise RuntimeError("api key xyz")
    patch_route(monkeypatch, "explain_sql", boom)
    r = client.post("/explain", json={"request_id": 5, "lang": "en"}, headers=bearer())
    assert r.status_code == 503 and "xyz" not in r.text


# ---------- alertas ----------

@pytest.fixture
def alert_data(monkeypatch):
    alerts_mod.clear_cache()
    calls = {"sales": 0}

    def run_query(sql, user):
        if "FROM stores" in sql and "sales" not in sql:
            return ["id", "name"], [(1, "Loja A"), (2, "Loja B")]
        calls["sales"] += 1
        return ["id", "name", "segment", "district", "last", "this_week", "last_week"], [
            (1, "Loja A", "hamburgueria", None, None, 800, 1000),     # -20 % → high
            (2, "Loja B", "café", None, None, 1120, 1000),            # +12 % → info
            (3, "Loja C", "café", None, None, 970, 1000),             # -3 %  → nada
            (4, "Gelado", "geladaria", None, None, 850, 1000),        # -15 %: normal numa geladaria → nada
        ]
    monkeypatch.setattr(alerts_mod, "run_query", run_query)
    monkeypatch.setattr(alerts_mod, "suggest_orders", lambda store, days: pd.DataFrame([
        {"store_id": 1, "ingredient": "Alface", "unit": "kg", "needed": 70.0, "stock": 2.0, "to_order": 68},   # 0,2 dias
        {"store_id": 2, "ingredient": "Pão", "unit": "un", "needed": 70.0, "stock": 4.5, "to_order": 66},     # 0,45 dias
        {"store_id": 2, "ingredient": "Óleo", "unit": "l", "needed": 70.0, "stock": 30.0, "to_order": 40},    # 3 dias
        {"store_id": 9, "ingredient": "Sal", "unit": "kg", "needed": 70.0, "stock": 0.1, "to_order": 70},     # loja não visível
    ]))
    yield calls
    alerts_mod.clear_cache()


def test_alerts_rules_and_order(alert_data):
    items = alerts_mod.alerts_for(IMPERADOR, "pt")
    assert [(a["type"], a["store"], a["severity"]) for a in items] == [
        ("sales_drop", "Loja A", "high"),
        ("low_stock", "Loja A", "high"),
        ("low_stock", "Loja B", "warn"),
        ("sales_rise", "Loja B", "info"),
    ]
    assert items[0]["message"] == "Loja A: vendas 20,0 % abaixo da semana anterior (800 € vs 1 000 €)."
    assert "Sal" not in json.dumps(items, ensure_ascii=False)        # só lojas que o RLS deixa ver


def test_alerts_are_translated_and_cached(alert_data):
    en = alerts_mod.alerts_for(IMPERADOR, "en")
    fr = alerts_mod.alerts_for(IMPERADOR, "fr")
    assert en[0]["message"].startswith("Loja A: sales 20.0% below") and "€1,000" in en[0]["message"]
    assert fr[0]["message"].startswith("Loja A : ventes 20,0 %")
    assert alert_data["sales"] == 1                                  # 2.º pedido veio da cache


def test_alerts_follow_the_modules(alert_data):
    only_sql = alerts_mod.alerts_for({**LOJA, "modules": ["sql"]}, "pt")
    assert {a["type"] for a in only_sql} == {"sales_drop", "sales_rise"}
    assert alerts_mod.alerts_for({**LOJA, "role": "marca", "brand_id": 1, "modules": ["teach"]}, "pt") == []


def test_alerts_never_break_the_chat(monkeypatch):
    alerts_mod.clear_cache()

    def boom(sql, user):
        raise psycopg.OperationalError("BD em baixo")
    monkeypatch.setattr(alerts_mod, "run_query", boom)
    assert alerts_mod.alerts_for(IMPERADOR, "pt") == []
    alerts_mod.clear_cache()


def test_alerts_endpoint_uses_the_accept_language(monkeypatch):
    seen = []
    patch_route(monkeypatch, "alerts_for", lambda user, lang: seen.append(lang) or [{"type": "x", "message": "m"}])
    r = client.get("/alerts", headers={**bearer(), "Accept-Language": "es-ES,es;q=0.9"})
    assert r.status_code == 200 and r.json() == {"alerts": [{"type": "x", "message": "m"}]} and seen == ["es"]


# ---------- perguntas de seguimento ----------

def test_suggestions_by_brand_with_a_month():
    out = suggestions("Faturação por marca em outubro?", "sql", ["marca", "faturacao"], [["A", 1], ["B", 2]], "pt")
    assert out == ["E por loja?", "Comparar com o mês anterior", "E por método de pagamento?"]


def test_suggestions_follow_the_profile():
    rows = [["Maia", 1]]
    assert "And by brand?" not in suggestions("Sales in 2026", "sql", ["loja", "total"], rows, "en", "loja")
    assert "And by brand?" not in suggestions("Sales in 2026", "sql", ["loja", "total"], rows, "en", "marca")
    assert "And by store?" in suggestions("Sales in 2026", "sql", ["marca", "total"], rows, "en", "marca")
    assert "And by store?" not in suggestions("Sales in 2026", "sql", ["marca", "total"], rows, "en", "loja")


def test_suggestions_for_long_store_lists():
    out = suggestions("Top lojas este ano", "sql", ["loja", "total"], [[i, i] for i in range(8)], "en")
    assert out == ["And by brand?", "Compare with last year", "Show only the top 3"]


@pytest.mark.parametrize("kind,first", [("forecast", "¿Qué ingredientes debo pedir?"),
                                        ("orders", "¿Cuánto venderé en los próximos 7 días?")])
def test_suggestions_after_ml_answers(kind, first):
    assert suggestions("q", kind, None, None, "es")[0] == first


def test_no_suggestions_for_chat_or_errors():
    assert suggestions("Olá", "no_sql", None, None) == [] and suggestions("q", "error", None, None) == []


def test_at_most_three_suggestions_and_unknown_language_falls_back():
    out = suggestions("vendas em 2026", "sql", ["marca", "faturacao"], [[1, 1]] * 3, "de")
    assert len(out) <= 3 and out[0] == "E por loja?"


# ---------- cache de SQL no ask() ----------

@pytest.fixture
def pipeline(monkeypatch):
    calls = {"generate": 0, "stored": [], "run": []}
    monkeypatch.setattr(ask_mod, "classify", lambda q: ("data", 0.9))
    monkeypatch.setattr(ask_mod, "answer", lambda *a, **k: "ok")

    def gen(q, h=None, failed=None):
        calls["generate"] += 1
        return "SELECT 2"
    monkeypatch.setattr(ask_mod, "generate_sql", gen)
    monkeypatch.setattr(ask_mod, "run_query", lambda s, u: calls["run"].append(s) or (["x"], [(1,)]))
    monkeypatch.setattr(ask_mod, "cache_store", lambda q, s, u: calls["stored"].append((q, s)))
    return calls


def test_cache_hit_skips_sql_generation(monkeypatch, pipeline):
    monkeypatch.setattr(ask_mod, "cache_lookup", lambda q, u: {"id": 1, "question": "q", "sql": "SELECT 1", "distance": 0.01})
    with obs.trace() as t:
        result = ask_mod.ask("Faturação?", LOJA, "pt")
    assert result["cached"] and result["sql"] == "SELECT 1" and pipeline["generate"] == 0
    assert pipeline["run"] == ["SELECT 1"] and t.cache_hit                # corre de novo com o RLS de quem pergunta


def test_cache_miss_generates_and_stores(monkeypatch, pipeline):
    monkeypatch.setattr(ask_mod, "cache_lookup", lambda q, u: None)
    result = ask_mod.ask("Faturação?", LOJA, "pt")
    assert not result.get("cached") and pipeline["generate"] == 1 and pipeline["stored"] == [("Faturação?", "SELECT 2")]


def test_cache_is_not_used_inside_a_conversation(monkeypatch, pipeline):
    monkeypatch.setattr(ask_mod, "cache_lookup", lambda q, u: pytest.fail("não devia consultar a cache"))
    ask_mod.ask("E no Porto?", LOJA, "pt", history=[("Faturação?", "SELECT 1")])
    assert pipeline["generate"] == 1 and pipeline["stored"] == []


def test_broken_cached_sql_falls_back_to_generation(monkeypatch, pipeline):
    monkeypatch.setattr(ask_mod, "cache_lookup", lambda q, u: {"id": 1, "question": "q", "sql": "DROP TABLE x", "distance": 0})
    result = ask_mod.ask("Faturação?", LOJA, "pt")
    assert result["sql"] == "SELECT 2" and pipeline["generate"] == 1


def test_ask_emits_events_in_order(monkeypatch, pipeline):
    monkeypatch.setattr(ask_mod, "cache_lookup", lambda q, u: None)
    events = []
    ask_mod.ask("Faturação?", LOJA, "pt", on_event=events.append)
    assert [e.get("step") or e["type"] for e in events] == ["classify", "sql", "query", "data", "answer"]


# ---------- chave da cache de SQL ----------

PAIRS = json.loads((Path(__file__).resolve().parents[2] / "eval" / "cache_pairs.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("part", ["tuning", "holdout"])
def test_different_questions_never_share_a_key(part):
    """Reaproveitar SQL errado devolve números errados com confiança: tem de ser 0."""
    clashes = [(a, b) for a, b in PAIRS[part]["different"] if question_key(a) == question_key(b)]
    assert clashes == []


def test_rewordings_share_a_key():
    same = PAIRS["tuning"]["same"] + PAIRS["holdout"]["same"]
    hits = sum(question_key(a) == question_key(b) for a, b in same)
    assert hits / len(same) >= 0.9                       # hoje 34/35; um acerto perdido só custa uma chamada ao LLM


@pytest.mark.parametrize("a,b", [
    ("Faturação de cada marca em outubro de 2026", "faturacao por MARCA em Outubro 2026?"),
    ("What was the revenue of each brand in October 2026?", "Facturación por marca en octubre de 2026"),
    ("Quantas lojas tem cada marca?", "How many stores does each brand have?"),
    ("Qual a faturação por método de pagamento?", "Revenue by payment method"),
])
def test_synonyms_across_languages(a, b):
    assert question_key(a) == question_key(b)


@pytest.mark.parametrize("a,b", [
    ("Quais as 5 lojas com mais faturação?", "Quais as 5 lojas com menos faturação?"),   # 0,067 no MiniLM
    ("Lojas com mais de 10 funcionários", "Top 10 lojas por funcionários"),
    ("Faturação por marca", "Faturação por marca sem a Gelato Mar"),
    ("Moyen de paiement par magasin", "Moyenne par magasin"),
])
def test_traps_the_embedding_falls_for(a, b):
    assert question_key(a) != question_key(b)


def test_unknown_words_are_kept_and_must_match():
    assert "maia" in question_key("Faturação da BurgerLab Maia") and question_key("Vendas") != question_key("Vendas Maia")


def test_monthly_breakdown_compares_with_last_year():
    out = suggestions("Faturação da minha loja por mês em 2026?", "sql", ["mes", "faturacao"], [[1, 1]] * 10, "pt", "loja")
    assert out[0] == "Comparar com o ano passado" and "Comparar com o mês anterior" not in out
    assert "Mostra só o top 3" not in out                                  # série temporal


def test_the_question_just_asked_is_not_suggested_again():
    out = suggestions("Comparar com o ano passado", "sql", ["mes", "faturacao"], [[1, 1]] * 12, "pt", "loja")
    assert "Comparar com o ano passado" not in out


# ---------- atalho "orders" do classificador ----------

def test_every_orders_training_phrase_keeps_the_shortcut():
    """A salvaguarda não pode tirar o atalho às frases de encomenda que o classificador aprendeu."""
    from multistore_ai_assistant.intent.dataset import EXTRA, SHORT
    phrases = EXTRA["orders"] + SHORT["orders"] + ["Que ingredientes devo encomendar?", "Quels ingrédients dois-je commander ?",
                                                    "¿Qué ingredientes debo pedir?", "Which ingredients should I order?"]
    assert [p for p in phrases if ask_mod.trust_shortcut("orders", p) != "orders"] == []


@pytest.mark.parametrize("question", ["Que produtos devo promover ou retirar da carta?", "Em que produtos devo mexer no preço?",
                                      "Which products should I promote or remove from the menu?"])
def test_menu_questions_misread_as_orders_go_to_the_llm(question):
    assert ask_mod.trust_shortcut("orders", question) is None
    assert ask_mod.trust_shortcut("forecast", question) == "forecast"          # só o atalho "orders" é verificado


def test_menu_question_reaches_the_sql_path(monkeypatch):
    monkeypatch.setattr(ask_mod, "classify", lambda q: ("orders", 0.999))
    monkeypatch.setattr(ask_mod, "generate_sql", lambda q, h=None, failed=None: "SELECT 1")
    monkeypatch.setattr(ask_mod, "run_query", lambda s, u: (["x"], [(1,)]))
    monkeypatch.setattr(ask_mod, "answer", lambda *a, **k: "ok")
    monkeypatch.setattr(ask_mod, "orders_answer", lambda u: pytest.fail("não devia ir ao modelo de encomendas"))
    assert ask_mod.ask("Que produtos devo promover ou retirar da carta?", LOJA, "pt")["kind"] == "sql"


def test_llm_quota_has_its_own_message(monkeypatch, conversation):
    import httpx
    from openai import RateLimitError

    def quota(*a, **k):
        response = httpx.Response(429, request=httpx.Request("POST", "https://llm.test/v1/chat/completions"))
        raise RateLimitError("tokens per day (TPD): Limit 200000", response=response, body=None)
    patch_route(monkeypatch, "ask", quota)
    r = client.post("/ask", json={"question": "q", "lang": "en"}, headers=bearer())
    assert r.status_code == 503 and r.json()["detail"]["code"] == "llm_quota"
    assert "usage limit" in r.json()["detail"]["message"] and "TPD" not in r.text


# ---------- alertas: limites por segmento e o tempo como contexto ----------

def test_ice_cream_shops_need_a_bigger_drop(monkeypatch):
    from datetime import date
    rows = [(9, "Gelato X", "geladaria", "Faro", date(2025, 8, 14), 700, 1000),   # -30 % → warn
            (8, "Gelato Y", "geladaria", "Faro", date(2025, 8, 14), 550, 1000)]   # -45 % → high
    monkeypatch.setattr(alerts_mod, "run_query", lambda sql, user: (["x"], rows))
    out = alerts_mod.sales_alerts(IMPERADOR)
    assert [(a["store"], a["severity"]) for a in out] == [("Gelato X", "warn"), ("Gelato Y", "high")]


def _weather_week(last, now, prev):
    """14 dias de tempo em Faro: ``now``/``prev`` = (máxima, chuva) de cada semana."""
    return {("Faro", last - alerts_mod.timedelta(days=i)): (now if i < 7 else prev) for i in range(14)}


def _gelato_alert(monkeypatch, w):
    from datetime import date
    last = date(2025, 8, 14)
    monkeypatch.setattr(alerts_mod, "weather", lambda: w(last))
    monkeypatch.setattr(alerts_mod, "run_query",
                        lambda sql, user: (["x"], [(9, "Gelato X", "geladaria", "Faro", last, 600, 1000)]))
    return alerts_mod.sales_alerts(IMPERADOR)[0]


def test_a_colder_week_is_mentioned(monkeypatch):
    a = _gelato_alert(monkeypatch, lambda last: _weather_week(last, (24.0, 0.0), (30.0, 0.0)))
    assert a["weather"] == {"temp_now": 24.0, "temp_prev": 30.0, "rain_days_now": 0, "rain_days_prev": 0}
    assert alerts_mod.message(a, "pt").endswith("Tempo: máxima média 24 °C vs 30 °C, 0 vs 0 dias de chuva.")
    assert "Weather: average high 24 °C vs 30 °C, 0 vs 0 rainy days." in alerts_mod.message(a, "en")


def test_a_rainy_week_is_mentioned_even_with_the_same_temperature(monkeypatch):
    a = _gelato_alert(monkeypatch, lambda last: _weather_week(last, (17.0, 20.0), (17.5, 0.0)))
    assert (a["weather"]["rain_days_now"], a["weather"]["rain_days_prev"]) == (7, 0)


def test_no_weather_note_when_the_weather_barely_changed(monkeypatch):
    a = _gelato_alert(monkeypatch, lambda last: _weather_week(last, (29.0, 0.0), (30.0, 0.0)))
    assert "weather" not in a and "Tempo" not in alerts_mod.message(a, "pt")
