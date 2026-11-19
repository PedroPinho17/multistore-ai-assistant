"""Gera SQL (ou etiquetas especiais) a partir de uma pergunta em linguagem natural.

O prompt inclui o esquema da BD, notas de negócio, exemplos RAG semelhantes
e o histórico da conversa. Em vez de SQL, o modelo pode responder exactamente:
``FORECAST``, ``ORDERS`` ou ``NO_SQL``.
"""
import os
import re
from datetime import date

from dotenv import load_dotenv
from openai import OpenAI

from multistore_ai_assistant.assistant.examples import find_similar
from multistore_ai_assistant.db.schema import get_schema_text
from multistore_ai_assistant.observability import record_llm

load_dotenv()

client = OpenAI(api_key=os.environ["GROQ_API_KEY"], base_url=os.environ["LLM_BASE_URL"])
MODEL = os.environ["LLM_MODEL"]

BUSINESS_NOTES = """
- Restaurant group with 3 brands: BurgerLab (burger restaurant), Café Aroma (café), Gelato Mar (ice cream kiosks).
- sales.total is the receipt amount in euros, VAT included. Revenue = SUM(sales.total).
- A sale_lines row has either product_id OR menu_id, never both.
- stock has either store_id OR warehouse_id (store stock vs warehouse stock).
- Stores receive ingredients through transfers from warehouses; warehouses buy from suppliers (purchases).
- purchases.status values: 'encomendada' (ordered) or 'recebida' (received).
- employees work either in a store (store_id) OR in a warehouse (warehouse_id).
- Data values (names, cities, categories) are in Portuguese.
- For cost, margin or profitability use the views product_margins and menu_margins (unit_cost, unit_margin, margin_pct per unit sold).
- Total margin of sales = sum(sale_lines.quantity * (sale_lines.unit_price - unit_cost)), joining product_margins on product_id or menu_margins on menu_id.
- For price recommendations, which products to promote or remove, use the view price_recommendations (classification: estrela, burro de carga, enigma, cão; recommendation text; last 90 days, compared within each brand).
- When the user says MB Way or MBWay, the payment_method value is 'mbway'.
- When filtering by a name (product, ingredient, store, brand), use ILIKE so case does not matter.
- Row-level security already limits every query to the user's own scope (their brand or their store). "My brand", "my store",
  "minha marca", "minha loja", "mi tienda", "ma marque" mean that scope: do NOT filter by a brand or store name for them,
  and never use placeholders or bind parameters (:marca, %(x)s, $1). Just query the tables.
"""

SYSTEM_PROMPT = """You are a PostgreSQL expert. Convert the user's question (in Portuguese, English, Spanish or French) into a single SELECT query.

Database schema:
{schema}

Business notes:
{notes}

Similar validated examples (follow their patterns when relevant):
{examples}


Rules:
- Reply with the SQL only, no explanations.
- Only SELECT (or WITH ... SELECT). Never INSERT, UPDATE, DELETE, DROP or ALTER.
- Use readable Portuguese column aliases with AS (e.g. AS faturacao).
- Round euro amounts to 2 decimal places.
- Unless the question asks for everything, limit to 100 rows.
- When filtering by a name (product, ingredient, store, brand), use ILIKE so case does not matter.
- If the user asks for a FUTURE sales/revenue forecast (next days, next week, "how much will I sell"), reply exactly: FORECAST
- If the user asks which ingredients to order, buy or restock, reply exactly: ORDERS
- If the user asks for personal employee data (NIF, NISS, address, birth date, phone, email), reply exactly: NO_SQL
- If the message is not a data question (greeting, off-topic, or a request to change data), reply exactly: NO_SQL
- Earlier turns of the conversation may come before the question. If the question is a follow-up (e.g. "and in September?", "only for Porto", "e no ano passado?"), adapt the previous SQL instead of starting from scratch.
- Today's date is {today}.
"""


def generate_sql(question: str, history: list[tuple[str, str]] | None = None) -> str:
    """Pede ao LLM um SELECT (ou FORECAST / ORDERS / NO_SQL).

    Args:
        question: Pergunta actual (ou prompt de retry com o erro da query).
        history: Trocas anteriores ``(pergunta, SQL|etiqueta)`` para follow-ups.

    Returns:
        SQL sem fences Markdown, ou uma das etiquetas especiais.
    """
    similar = find_similar(question)
    examples = "\n\n".join(f"Q: {q}\nSQL: {s}" for q, s in similar) or "(none)"
    prompt = SYSTEM_PROMPT.format(
        schema=get_schema_text(),
        notes=BUSINESS_NOTES,
        examples=examples,
        today=date.today().isoformat(),
    )
    messages = [{"role": "system", "content": prompt}]
    for q, s in history or []:
        messages.append({"role": "user", "content": q})
        messages.append({"role": "assistant", "content": s})
    messages.append({"role": "user", "content": question})
    response = client.chat.completions.create(model=MODEL, messages=messages, temperature=0)
    record_llm(response)
    text = response.choices[0].message.content or ""
    # Remove ```sql ... ``` se o modelo as tiver posto; tira o ; final
    return re.sub(r"```(?:sql)?", "", text).strip().rstrip(";")


if __name__ == "__main__":
    print(generate_sql("Qual foi a faturação de cada marca em outubro de 2026?"))
