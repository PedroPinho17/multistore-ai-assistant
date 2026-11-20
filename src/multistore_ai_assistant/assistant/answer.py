"""Transforma o resultado da query (ou previsão) numa resposta em linguagem natural.

Usa o mesmo cliente/modelo Groq que o gerador de SQL. Há dois caminhos:
- ``answer``: resume linhas da BD / forecast.
- ``chat_reply``: cumprimentos e recusas sem dados (nunca inventa números).
"""
from multistore_ai_assistant.assistant.sql_generator import MODEL, client
from multistore_ai_assistant.observability import record_llm

MAX_ROWS_IN_PROMPT = 50
LANGUAGES = {
    "pt": "European Portuguese (pt-PT)",
    "en": "English",
    "es": "Spanish (Spain)",
    "fr": "French (France)",
}

SYSTEM_PROMPT = """You are a data assistant for a Portuguese restaurant group.
Answer in {language}.

Rules:
- Be short: 1 to 3 sentences.
- Mention the key numbers; format euros like 461 704,40 €.
- Never invent data that is not in the result.
- If the result is empty, say that no data was found.
- Do not mention SQL, tables or columns.
- Answer exactly what was asked. If no row matches the request, say so instead of picking another row.
- If there are more than 5 rows, do NOT list them all: summarise the highlights in 1-3 sentences (the table is shown below the answer).
- Plain text only: no Markdown, no asterisks, no bullet lists.
- NEVER copy the table into the text (no "|", no list of every row).
- Only state facts you can read directly from the rows (total, max, min). Do not estimate ranges or typical values.
"""


def complete(messages: list[dict], temperature: float, on_token=None) -> str:
    """Chama o LLM; com ``on_token`` a resposta chega aos bocados (streaming).

    Em streaming, os tokens gastos vêm no último pedaço (``include_usage``),
    por isso o registo de observabilidade continua certo.
    """
    if on_token is None:
        response = client.chat.completions.create(model=MODEL, messages=messages, temperature=temperature)
        record_llm(response)
        return (response.choices[0].message.content or "").strip()
    stream = client.chat.completions.create(model=MODEL, messages=messages, temperature=temperature,
                                            stream=True, stream_options={"include_usage": True})
    parts, usage = [], None
    try:
        for chunk in stream:
            if getattr(chunk, "usage", None):
                usage = chunk
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                piece = chunk.choices[0].delta.content
                parts.append(piece)
                on_token(piece)          # levanta se o cliente do streaming se desligou
    finally:
        if close := getattr(stream, "close", None):
            close()                      # fecha já o pedido HTTP ao LLM (não espera pelo garbage collector)
    record_llm(usage)
    return "".join(parts).strip()


def answer(question: str, columns: list[str], rows: list[tuple], lang: str = "pt", on_token=None) -> str:
    """Resume o resultado tabular numa resposta curta no idioma pedido.

    Args:
        question: Pergunta original (ou nota de forecast).
        columns: Nomes das colunas do resultado.
        rows: Linhas (até ``MAX_ROWS_IN_PROMPT`` entram no prompt).
        lang: Código de idioma da UI.
        on_token: Opcional; recebe cada pedaço do texto (streaming).

    Returns:
        Texto curto sem Markdown.
    """
    header = " | ".join(columns)
    lines = "\n".join(" | ".join(str(v) for v in row) for row in rows[:MAX_ROWS_IN_PROMPT])
    extra = (
        f"\n(+{len(rows) - MAX_ROWS_IN_PROMPT} more rows)"
        if len(rows) > MAX_ROWS_IN_PROMPT else ""
    )

    return complete([
        {"role": "system", "content": SYSTEM_PROMPT.format(language=LANGUAGES[lang])},
        {"role": "user", "content": f"Question: {question}\n\nResult:\n{header}\n{lines}{extra}"},
    ], 0.2, on_token)


CHAT_PROMPT = """You are the data assistant of a Portuguese restaurant group
(brands: BurgerLab, Café Aroma, Gelato Mar). You answer questions about sales, stores,
products, menus, stock, purchases, transfers, employees and shifts.

The user's message could NOT be answered with a database query.
You have NO access to any data in this reply.

Answer in {language}.
in 1-2 friendly sentences:
- greetings or thanks: reply naturally and say what you can help with;
- requests to change/delete data: politely say you only read data;
- personal data (NIF, NISS, address, birth date): say this data is protected (GDPR) and not available;
- off-topic questions: say it's outside your scope and suggest an example data question.

NEVER write names, numbers, tables, examples of records or any data. NEVER invent information.
"""


def chat_reply(message: str, lang: str = "pt", on_token=None) -> str:
    """Resposta amigável sem dados (cumprimentos, recusas, fora de âmbito).

    Args:
        message: Mensagem do utilizador.
        lang: Idioma da resposta.

    Returns:
        1–2 frases; nunca inventa factos da BD.
    """
    return complete([
        {"role": "system", "content": CHAT_PROMPT.format(language=LANGUAGES[lang])},
        {"role": "user", "content": message},
    ], 0.5, on_token)


EXPLAIN_PROMPT = """You explain SQL queries to restaurant managers who don't know SQL.
Answer in {language}, in plain text (no Markdown, no code), in 2 to 4 short sentences:
what data it reads (in business words: sales, stores, products...), how it filters
(period, store, brand) and how it groups or orders the result.
Never mention table aliases, joins or SQL keywords.
"""


def explain_sql(sql: str, lang: str = "pt") -> str:
    """Explica um SELECT em linguagem simples (botão «Explicar» na Fonte)."""
    return complete([
        {"role": "system", "content": EXPLAIN_PROMPT.format(language=LANGUAGES[lang])},
        {"role": "user", "content": sql},
    ], 0.2)
