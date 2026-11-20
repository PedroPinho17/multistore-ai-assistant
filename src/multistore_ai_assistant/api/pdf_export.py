"""Exportação de conversas para PDF (ReportLab), só do lado do servidor.

Inclui título, pares pergunta/resposta, o SQL quando existir e as tabelas que o
utilizador viu: as linhas guardadas com cada resposta (``messages.result``, até 200).
Nada é reexecutado (SQL, previsão ou encomendas): o PDF mostra exatamente o que
foi respondido, mesmo para "ontem" ou "este mês", e não contorna os módulos da conta.
Respostas antigas, sem linhas guardadas, dizem "tabela não disponível".

Fonte DejaVu Sans (incluída em ``api/fonts``, licença em ``LICENSE-DejaVu.txt``):
as fontes base do PDF não têm símbolos como → ou ≈.
"""
import logging
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from multistore_ai_assistant.api.errors import _

log = logging.getLogger("multistore")

FONT_DIR = Path(__file__).resolve().parent / "fonts"
FONT, FONT_BOLD, FONT_MONO = "DejaVuSans", "DejaVuSans-Bold", "DejaVuSansMono"
for _name in (FONT, FONT_BOLD, FONT_MONO):
    pdfmetrics.registerFont(TTFont(_name, str(FONT_DIR / f"{_name}.ttf")))
pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=FONT_BOLD, italic=FONT, boldItalic=FONT_BOLD)

WIDE_COLUMNS = 6           # mais colunas do que isto numa tabela: página na horizontal
MARGIN = 16 * mm
TABLE_KINDS = ("sql", "forecast", "orders")   # respostas que mostraram uma tabela

LABELS = {
    "title": _("Conversa", "Conversation", "Conversación", "Conversation"),
    "question": _("Pergunta", "Question", "Pregunta", "Question"),
    "answer": _("Resposta", "Answer", "Respuesta", "Réponse"),
    "sql": _("SQL", "SQL", "SQL", "SQL"),
    "table": _("Tabela", "Table", "Tabla", "Tableau"),
    "empty": _("(sem conteúdo)", "(no content)", "(sin contenido)", "(sans contenu)"),
    "no_table": _("Tabela não disponível (resposta anterior à exportação para PDF).",
                  "Table not available (answer from before PDF export existed).",
                  "Tabla no disponible (respuesta anterior a la exportación a PDF).",
                  "Tableau non disponible (réponse antérieure à l'export PDF)."),
    "truncated": _("Mostradas só as primeiras {n} linhas.", "Only the first {n} rows are shown.",
                   "Solo se muestran las primeras {n} filas.", "Seules les {n} premières lignes sont affichées."),
}


def _label(key: str, lang: str, **params) -> str:
    entry = LABELS[key]
    return (entry.get(lang) or entry["pt"]).format(**params)


def _markup(text) -> str:
    """Texto seguro para um Paragraph (escapa a marcação) e com as quebras de linha mantidas."""
    text = "" if text is None else str(text)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _styles() -> dict[str, ParagraphStyle]:
    base = {"fontName": FONT, "alignment": TA_LEFT}
    return {
        "h1": ParagraphStyle("H1", **{**base, "fontName": FONT_BOLD}, fontSize=16, leading=20, spaceAfter=12,
                             textColor=colors.HexColor("#0b6b4e")),
        "label": ParagraphStyle("Lbl", **base, fontSize=9, leading=11, textColor=colors.HexColor("#5c6b66"),
                                spaceBefore=10, spaceAfter=2),
        "body": ParagraphStyle("Body", **base, fontSize=11, leading=15, spaceAfter=4),
        "note": ParagraphStyle("Note", **base, fontSize=8, leading=10, textColor=colors.HexColor("#5c6b66"),
                               spaceBefore=2),
        "mono": ParagraphStyle("Mono", **{**base, "fontName": FONT_MONO}, fontSize=8, leading=11,
                               textColor=colors.HexColor("#1a1a1a"), backColor=colors.HexColor("#f3f5f4"),
                               spaceAfter=6),
        "cell": ParagraphStyle("Cell", **base, fontSize=8, leading=10),
        "head": ParagraphStyle("Head", **{**base, "fontName": FONT_BOLD}, fontSize=8, leading=10,
                               textColor=colors.white),
    }


def column_widths(columns: list, rows: list, width: float) -> list[float]:
    """Larguras proporcionais ao conteúdo (com mínimo e máximo), que somam exatamente ``width``."""
    weights = []
    for i, col in enumerate(columns):
        longest = max([len(str(col))] + [len(_cell(r[i])) for r in rows if i < len(r)])
        weights.append(min(max(longest, 4), 40))           # nem colunas minúsculas nem uma a comer tudo
    total = sum(weights)
    return [width * w / total for w in weights]


def table_block(columns: list, rows: list, width: float, styles: dict | None = None) -> Table | None:
    """Tabela com o texto das células a quebrar linha e as colunas a caber em ``width``."""
    if not columns:
        return None
    styles = styles or _styles()
    data = [[Paragraph(_markup(c), styles["head"]) for c in columns]]
    for row in rows:
        data.append([Paragraph(_markup(_cell(v)), styles["cell"]) for v in row])
    tbl = Table(data, colWidths=column_widths(columns, rows, width), repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f7a5a")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c5cec9")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f3f5f4")]),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return tbl


def stored_table(msg: dict) -> dict | None:
    """As linhas guardadas de uma resposta, ou ``None`` (sem dados ou dados num formato inesperado)."""
    result = msg.get("result")
    if result is None:
        return None
    if not (isinstance(result, dict) and isinstance(result.get("columns"), list)
            and isinstance(result.get("rows"), list)):
        log.warning("PDF: dados guardados inválidos numa mensagem (%s); a tabela fica de fora", type(result).__name__)
        return None
    return result


def page_size(messages: list[dict]) -> tuple[float, float]:
    """A4 ao alto; na horizontal se alguma tabela tiver muitas colunas."""
    wide = any(len(t["columns"]) > WIDE_COLUMNS
               for m in messages if m.get("role") == "assistant" and (t := stored_table(m)))
    return landscape(A4) if wide else A4


def build_story(title: str, messages: list[dict], lang: str, width: float) -> list:
    """Os blocos do PDF (títulos, textos, SQL, tabelas), com as tabelas a caber em ``width``."""
    styles = _styles()
    story: list = [Paragraph(_markup(title or _label("title", lang)), styles["h1"])]

    def add_assistant(ans: dict) -> None:
        story.append(Paragraph(_label("answer", lang), styles["label"]))
        story.append(Paragraph(_markup(ans.get("content") or _label("empty", lang)), styles["body"]))
        if ans.get("sql"):
            story.append(Paragraph(_label("sql", lang), styles["label"]))
            story.append(Paragraph(_markup(ans["sql"]), styles["mono"]))
        if ans.get("kind") not in TABLE_KINDS:
            return
        stored = stored_table(ans)
        if stored is None:
            story.append(Paragraph(_label("no_table", lang), styles["note"]))
            return
        tbl = table_block(stored["columns"], stored["rows"], width, styles)
        if tbl is not None:
            story.append(Paragraph(_label("table", lang), styles["label"]))
            story.append(tbl)
            if stored.get("truncated"):
                story.append(Paragraph(_label("truncated", lang, n=len(stored["rows"])), styles["note"]))

    i = 0
    while i < len(messages):
        msg = messages[i]
        if msg.get("role") == "user":
            story.append(Paragraph(_label("question", lang), styles["label"]))
            story.append(Paragraph(_markup(msg.get("content") or _label("empty", lang)), styles["body"]))
            if i + 1 < len(messages) and messages[i + 1].get("role") == "assistant":
                add_assistant(messages[i + 1])
                i += 2
            else:
                i += 1
        else:
            add_assistant(msg)
            i += 1
        story.append(Spacer(1, 4))

    if not messages:
        story.append(Paragraph(_label("empty", lang), styles["body"]))
    return story


def conversation_pdf(title: str, messages: list[dict], lang: str = "pt") -> bytes:
    """Gera o PDF da conversa a partir das mensagens guardadas (``get_messages(with_results=True)``)."""
    buf = BytesIO()
    size = page_size(messages)
    doc = SimpleDocTemplate(buf, pagesize=size, leftMargin=MARGIN, rightMargin=MARGIN,
                            topMargin=MARGIN, bottomMargin=MARGIN, title=title or _label("title", lang))
    doc.build(build_story(title, messages, lang, doc.width))
    return buf.getvalue()
