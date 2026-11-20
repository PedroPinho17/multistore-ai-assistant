"""GET /conversations/{id}/pdf e o PDF em si (BD simulada).

O PDF usa só as linhas guardadas com cada resposta: nada é reexecutado. Como o texto
fica numa fonte TrueType embebida (ilegível nos bytes do PDF), o conteúdo é verificado
nos blocos que ``build_story`` monta.
"""
import base64
import re
import zlib

import pytest
from fastapi.testclient import TestClient
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import Paragraph, Table

from multistore_ai_assistant.api import auth, conversations, pdf_export
from multistore_ai_assistant.api import main as api
from multistore_ai_assistant.db import query
from multistore_ai_assistant.forecast import service
from tests.conftest import IMPERADOR, LOJA, patch_route

client = TestClient(api.app)
WIDTH = A4[0] - 2 * pdf_export.MARGIN


def bearer(user=LOJA) -> dict:
    return {"Authorization": "Bearer " + auth.create_token(user)}


def result(columns, rows, truncated=False):
    return {"columns": columns, "rows": rows, "truncated": truncated}


MSGS = [
    {"role": "user", "content": "Faturação por marca?", "sql": None, "kind": None, "result": None},
    {"role": "assistant", "content": "A BurgerLab → 10 €.", "sql": "SELECT 1", "kind": "sql",
     "result": result(["marca", "faturacao"], [["BurgerLab", 10.0], ["Café Aroma", 2.5]])},
]


def texts(story) -> list[str]:
    """Todo o texto dos blocos (parágrafos e células das tabelas)."""
    out = []
    for block in story:
        if isinstance(block, Paragraph):
            out.append(block.text)
        elif isinstance(block, Table):
            out += [cell.text for row in block._cellvalues for cell in row]
    return out


def tables(story) -> list[Table]:
    return [b for b in story if isinstance(b, Table)]


@pytest.fixture
def conv(monkeypatch):
    """Conversa 7 do gerente.maia; ``seen`` guarda como as mensagens foram pedidas."""
    seen = []

    def get_messages(u, c, with_results=False):
        seen.append(with_results)
        return MSGS if c == 7 and u == "gerente.maia" else None
    patch_route(monkeypatch, "conversation_title", lambda u, c: "Vendas" if c == 7 and u == "gerente.maia" else None)
    patch_route(monkeypatch, "get_messages", get_messages)
    return seen


@pytest.fixture
def nothing_runs(monkeypatch):
    """Falha o teste se o PDF tentar correr SQL, a previsão ou as encomendas."""
    def boom(*a, **k):
        pytest.fail("o PDF não pode reexecutar nada")
    monkeypatch.setattr(query, "run_query", boom)
    for name in ("forecast_answer", "orders_answer", "forecast", "suggest_orders"):
        monkeypatch.setattr(service, name, boom)


# ---------- endpoint ----------

def test_pdf_requires_login():
    assert client.get("/conversations/7/pdf").status_code in (401, 403)


def test_pdf_of_own_conversation_uses_the_stored_rows(conv, nothing_runs):
    r = client.get("/conversations/7/pdf", headers=bearer())
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    assert r.headers["content-type"] == "application/pdf"
    assert 'filename="Vendas.pdf"' in r.headers["content-disposition"]
    assert conv == [True]                                     # pediu as mensagens com as linhas guardadas


def test_without_the_sql_module_the_pdf_still_shows_what_was_answered(conv, nothing_runs, fake_users):
    fake_users["gerente.maia"] = {**LOJA, "modules": ["forecast"]}
    assert client.get("/conversations/7/pdf", headers=bearer(fake_users["gerente.maia"])).status_code == 200


def test_pdf_of_other_users_conversation_is_404(conv):
    r = client.get("/conversations/7/pdf", headers=bearer(IMPERADOR))
    assert r.status_code == 404 and r.json()["detail"]["code"] == "conv_not_found"


def test_pdf_unknown_conversation_is_404(conv):
    assert client.get("/conversations/999/pdf", headers=bearer()).status_code == 404


def test_pdf_has_its_own_rate_limit(conv, nothing_runs):
    codes = [client.get("/conversations/7/pdf", headers=bearer()).status_code for _ in range(6)]
    assert codes == [200] * 5 + [429]
    assert client.get("/conversations", headers=bearer()).status_code != 429   # o resto das conversas não é afetado


# ---------- conteúdo ----------

def test_stored_rows_are_the_table():
    story = pdf_export.build_story("Vendas", MSGS, "pt", WIDTH)
    assert len(tables(story)) == 1
    all_text = texts(story)
    assert "BurgerLab" in all_text and "2.5" in all_text and "10" in all_text   # 10.0 aparece como 10
    assert "A BurgerLab → 10 €." in all_text


def test_old_answers_without_rows_say_the_table_is_not_available():
    old = [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a", "kind": "sql", "sql": "SELECT 1"}]
    story = pdf_export.build_story("t", old, "en", WIDTH)
    assert tables(story) == []
    assert any(t.startswith("Table not available") for t in texts(story))


def test_answers_without_a_table_have_no_table_note():
    chat = [{"role": "user", "content": "Olá"}, {"role": "assistant", "content": "Olá!", "kind": "no_sql"}]
    assert not any("indisponível" in t or "não disponível" in t for t in texts(pdf_export.build_story("t", chat, "pt", WIDTH)))


def test_truncated_rows_are_noted():
    msgs = [{"role": "assistant", "content": "a", "kind": "sql",
             "result": result(["n"], [[i] for i in range(200)], truncated=True)}]
    story = pdf_export.build_story("t", msgs, "fr", WIDTH)
    assert "Seules les 200 premières lignes sont affichées." in texts(story)
    assert len(tables(story)[0]._cellvalues) == 201                              # cabeçalho + 200


def test_malformed_stored_rows_are_logged_not_fatal(caplog):
    msgs = [{"role": "assistant", "content": "a", "kind": "sql", "result": ["isto", "não"]}]
    with caplog.at_level("WARNING", logger="multistore"):
        story = pdf_export.build_story("t", msgs, "pt", WIDTH)
    assert tables(story) == [] and any("inválidos" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("lang,question,answer", [("pt", "Pergunta", "Resposta"), ("en", "Question", "Answer"),
                                                  ("es", "Pregunta", "Respuesta"), ("fr", "Question", "Réponse")])
def test_labels_in_four_languages(lang, question, answer):
    all_text = texts(pdf_export.build_story("t", MSGS, lang, WIDTH))
    assert question in all_text and answer in all_text


def test_markup_in_answers_is_escaped_and_line_breaks_kept():
    msgs = [{"role": "assistant", "content": "<b>x</b> & y\nlinha 2", "kind": "no_sql"}]
    assert "&lt;b&gt;x&lt;/b&gt; &amp; y<br/>linha 2" in texts(pdf_export.build_story("t", msgs, "pt", WIDTH))


# ---------- paginação, larguras e fonte ----------

def wide_msgs(columns=9, text="valor comprido"):
    cols = [f"coluna_{i}" for i in range(columns)]
    return [{"role": "assistant", "content": "a", "kind": "sql",
             "result": result(cols, [[f"{text} {r}-{c}" for c in range(columns)] for r in range(3)])}]


def test_many_columns_turn_the_page_to_landscape():
    assert pdf_export.page_size(MSGS) == A4
    assert pdf_export.page_size(wide_msgs(pdf_export.WIDE_COLUMNS)) == A4
    assert pdf_export.page_size(wide_msgs(pdf_export.WIDE_COLUMNS + 1)) == landscape(A4)


@pytest.mark.parametrize("columns", [2, 9, 20])
def test_tables_always_fit_the_page_width(columns):
    msgs = wide_msgs(columns)
    width = pdf_export.page_size(msgs)[0] - 2 * pdf_export.MARGIN
    tbl = tables(pdf_export.build_story("t", msgs, "pt", width))[0]
    assert sum(tbl._colWidths) == pytest.approx(width)
    assert tbl.wrap(width, 10_000)[0] <= width + 0.01           # antes: 960 pt numa página de 493 pt


def test_long_cell_text_wraps_instead_of_overflowing():
    long = "palavra " * 60
    msgs = [{"role": "assistant", "content": "a", "kind": "sql", "result": result(["a", "b"], [[long, "x"]])}]
    tbl = tables(pdf_export.build_story("t", msgs, "pt", WIDTH))[0]
    width, height = tbl.wrap(WIDTH, 10_000)
    assert width <= WIDTH + 0.01 and height > 40                # várias linhas dentro da célula


def test_column_widths_follow_the_content():
    widths = pdf_export.column_widths(["id", "descricao"], [[1, "uma descrição bastante comprida"]], 300)
    assert sum(widths) == pytest.approx(300) and widths[1] > widths[0] * 3


def fonts_that_draw_text(pdf: bytes) -> set[str]:
    """BaseFont de cada fonte usada em blocos de texto que desenham letras (Tj/TJ).

    O ReportLab declara sempre a Helvetica (/F1) no início de cada página
    (``BT /F1 12 Tf 14.4 TL ET``), sem desenhar nada com ela: isso não conta.
    """
    base = {name.decode(): font.decode() for name, font in
            re.findall(rb"/(F\d+(?:\+\d+)?) (\d+) 0 R", pdf)}
    base = {name: re.search(rb"%s 0 obj\s*<<.*?/BaseFont\s*/([\w+\-]+)" % num.encode(), pdf, re.S).group(1).decode()
            for name, num in base.items()}
    used = set()
    for head, raw in re.findall(rb"<<([^>]*?)>>\s*stream\r?\n(.*?)endstream", pdf, re.S):
        data = raw.strip()
        if b"ASCII85" in head:
            data = base64.a85decode(data[:-2] if data.endswith(b"~>") else data)
        if b"Flate" in head:
            try:
                data = zlib.decompress(data)
            except zlib.error:
                continue
        for block in re.findall(rb"BT(.*?)ET", data, re.S):
            if re.search(rb"T[jJ]\b", block):
                used |= {base[f.decode()] for f in re.findall(rb"/(F\d+(?:\+\d+)?) [\d.]+ Tf", block)}
    return used


def test_the_pdf_draws_all_text_in_dejavu():
    msgs = [{"role": "user", "content": "Ação → ≈ 5 %? Café, pão, coração"},
            {"role": "assistant", "content": "Sim ≈ 5 %", "kind": "sql", "sql": "SELECT 'São João'",
             "result": result(["loja", "variação"], [["Café Aroma", "↑ 5 %"]])}]
    pdf = pdf_export.conversation_pdf("Previsão ≈", msgs, "pt")
    used = fonts_that_draw_text(pdf)
    assert used and all("DejaVuSans" in f for f in used), used   # texto, títulos, SQL (Mono) e tabela
    assert any(f.endswith("DejaVuSansMono") for f in used)


def test_long_conversations_build_without_errors():
    msgs = []
    for i in range(30):
        msgs += [{"role": "user", "content": f"Pergunta {i}"},
                 {"role": "assistant", "content": "Resposta " * 50, "kind": "sql", "sql": "SELECT " + "x, " * 80 + "1",
                  "result": result(["a", "b", "c"], [[j, "texto", j * 1.5] for j in range(40)])}]
    assert pdf_export.conversation_pdf("Longa", msgs, "pt")[:4] == b"%PDF"


def test_stored_payload_is_capped_at_200_rows():
    import json
    payload = json.loads(conversations.result_payload(["n"], [(i,) for i in range(250)]))
    assert len(payload["rows"]) == conversations.MAX_STORED_ROWS and payload["truncated"] is True
    assert json.loads(conversations.result_payload(["n"], [(1,)]))["truncated"] is False
    assert conversations.result_payload(None, None) is None
