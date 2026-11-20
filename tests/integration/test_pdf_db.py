"""Exportação PDF de conversas na BD real (só as próprias)."""
import os

import bcrypt
import psycopg
import pytest
from fastapi.testclient import TestClient

from multistore_ai_assistant.api import auth
from multistore_ai_assistant.api import conversations as conv
from multistore_ai_assistant.api import main as api

pytestmark = pytest.mark.integration
TMP = "pytest.pdfuser"

try:
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=3) as _c:
        _ok = _c.execute("SELECT to_regclass('public.conversations') IS NOT NULL").fetchone()[0]
except Exception:
    _ok = False
if not _ok:
    pytest.skip("Base de dados indisponível", allow_module_level=True)

client = TestClient(api.app)


@pytest.fixture
def tmp_user():
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as c:
        store_id = c.execute("SELECT id FROM stores ORDER BY id LIMIT 1").fetchone()[0]
        c.execute("DELETE FROM users WHERE username = %s", (TMP,))
        c.execute(
            "INSERT INTO users (username, password_hash, role, store_id) VALUES (%s, %s, 'loja', %s)",
            (TMP, bcrypt.hashpw(b"PdfPass2026", bcrypt.gensalt(rounds=4)).decode(), store_id),
        )
        user = auth.load_user(TMP)
        yield user
        c.execute("DELETE FROM users WHERE username = %s", (TMP,))


def test_pdf_of_own_conversation_roundtrip(tmp_user):
    cid = conv.create_conversation(TMP, "Faturação de ontem?")
    conv.add_message(cid, "user", "Faturação de ontem?")
    conv.add_message(cid, "assistant", "Foram 42 €.", "SELECT 1 AS n", "sql")
    r = client.get(
        f"/conversations/{cid}/pdf",
        headers={"Authorization": "Bearer " + auth.create_token(tmp_user), "Accept-Language": "en"},
    )
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    assert "application/pdf" in r.headers["content-type"]


def test_cannot_export_someone_elses_conversation(tmp_user):
    other = conv.create_conversation("gerente.maia", "Privada")
    try:
        r = client.get(
            f"/conversations/{other}/pdf",
            headers={"Authorization": "Bearer " + auth.create_token(tmp_user)},
        )
        assert r.status_code == 404
    finally:
        conv.delete_conversation("gerente.maia", other)


# ---------- linhas guardadas com a resposta (o PDF nunca reexecuta) ----------

def bearer(user) -> dict:
    return {"Authorization": "Bearer " + auth.create_token(user)}


def test_stored_rows_roundtrip_with_decimals_and_dates(tmp_user):
    from datetime import date
    from decimal import Decimal
    cid = conv.create_conversation(TMP, "Vendas?")
    conv.add_message(cid, "assistant", "ok", "SELECT 1", "sql", None,
                     conv.result_payload(["dia", "total"], [(date(2026, 11, 19), Decimal("10.50"))]))
    stored = conv.get_messages(TMP, cid, with_results=True)[0]["result"]
    assert stored == {"columns": ["dia", "total"], "rows": [["2026-11-19", 10.5]], "truncated": False}
    assert "result" not in conv.get_messages(TMP, cid)[0]         # a UI não recebe as linhas


def test_more_than_200_rows_are_capped_and_the_db_refuses_bigger_payloads(tmp_user):
    import json
    cid = conv.create_conversation(TMP, "Muitas linhas")
    conv.add_message(cid, "assistant", "ok", "SELECT 1", "sql", None,
                     conv.result_payload(["n"], [(i,) for i in range(500)]))
    stored = conv.get_messages(TMP, cid, with_results=True)[0]["result"]
    assert len(stored["rows"]) == 200 and stored["truncated"] is True
    too_big = json.dumps({"columns": ["n"], "rows": [[i] for i in range(201)], "truncated": False})
    with pytest.raises(psycopg.errors.CheckViolation):
        conv.add_message(cid, "assistant", "x", None, "sql", None, too_big)


def test_pdf_shows_what_was_answered_not_todays_data(tmp_user, monkeypatch):
    """"Faturação de ontem?" exportada dias depois: a tabela é a da resposta, não a de hoje."""
    from multistore_ai_assistant.db import query
    monkeypatch.setattr(query, "run_query", lambda *a, **k: pytest.fail("o PDF não pode correr SQL"))
    cid = conv.create_conversation(TMP, "Faturação de ontem?")
    conv.add_message(cid, "user", "Faturação de ontem?")
    conv.add_message(cid, "assistant", "Foram 42 €.", "SELECT …", "sql", None,
                     conv.result_payload(["faturacao"], [(42,)]))
    r = client.get(f"/conversations/{cid}/pdf", headers=bearer(tmp_user))
    assert r.status_code == 200 and r.content[:4] == b"%PDF"


def test_answers_through_the_api_store_their_rows_for_the_pdf(tmp_user, monkeypatch):
    """De ponta a ponta: /ask grava as linhas e o PDF usa-as (sem LLM; o SQL corre uma vez, no /ask)."""
    from multistore_ai_assistant.api.routes import ask as ask_route
    rows = [("BurgerLab Maia", 100.0), ("Gelato Mar Maia", 50.0)]
    monkeypatch.setattr(ask_route, "ask", lambda q, u, lang, h, on_event=None: {
        "sql": "SELECT name, total FROM x", "kind": "sql", "columns": ["loja", "total"], "rows": rows,
        "answer": "Duas lojas."})
    body = client.post("/ask", json={"question": "Lojas da Maia?", "lang": "pt"}, headers=bearer(tmp_user)).json()
    stored = conv.get_messages(TMP, body["conversation_id"], with_results=True)[-1]["result"]
    assert stored["rows"] == [list(r) for r in rows]
    from multistore_ai_assistant.api import pdf_export
    story = pdf_export.build_story("t", conv.get_messages(TMP, body["conversation_id"], with_results=True),
                                   "pt", 400)
    cells = [c.text for b in story if hasattr(b, "_cellvalues") for row in b._cellvalues for c in row]
    assert "Gelato Mar Maia" in cells
