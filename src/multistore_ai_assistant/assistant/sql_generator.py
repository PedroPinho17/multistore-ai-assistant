"""Gera SQL (ou etiquetas especiais) a partir de uma pergunta em linguagem natural.

O prompt inclui o esquema da BD, notas de negócio, exemplos RAG semelhantes
e o histórico da conversa. Em vez de SQL, o modelo pode responder exactamente:
``FORECAST``, ``ORDERS`` ou ``NO_SQL``.
"""
import os
import re
from datetime import date

from dotenv import load_dotenv

from multistore_ai_assistant.assistant.examples import find_similar
from multistore_ai_assistant.assistant.llm import llm_client
from multistore_ai_assistant.db.schema import get_schema_text
from multistore_ai_assistant.observability import record_llm

load_dotenv()

client = llm_client()     # GROQ_API_KEY e, se a quota acabar, GROQ_API_KEY_FALLBACK
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
- Store names are "<brand> <city>" (e.g. 'BurgerLab Maia', 'Café Aroma Porto'); users usually say only part of them.
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
- When filtering by a name (store, brand, product, ingredient), use ILIKE with % on both sides, so case
  and partial names still match: st.name ILIKE '%Maia%', never st.name = 'Maia' or st.name ILIKE 'Maia'.
  Example:
  Q: Quanto queijo cheddar há na loja de Coimbra?
  SQL: SELECT st.name AS loja, i.name AS ingrediente, s.quantity AS quantidade, i.unit AS unidade
       FROM stock s JOIN stores st ON st.id = s.store_id JOIN ingredients i ON i.id = s.ingredient_id
       WHERE st.name ILIKE '%Coimbra%' AND i.name ILIKE '%cheddar%'
- If the user asks for a FUTURE sales/revenue forecast (next days, next week, "how much will I sell"), reply exactly: FORECAST
- If the user asks which ingredients to order, buy or restock, reply exactly: ORDERS
- If the user asks for personal employee data (NIF, NISS, address, birth date, phone, email), reply exactly: NO_SQL
- If the message is not a data question (greeting, off-topic, or a request to change data), reply exactly: NO_SQL
- Earlier turns of the conversation may come before the question. If the question is a follow-up (e.g. "and in September?", "only for Porto", "e no ano passado?"), adapt the previous SQL instead of starting from scratch.
- Today's date is {today}.
"""


FIX_PROMPT = """That query failed with this error:
{error}

Reply with a corrected query for the same question (SQL only), or with one of the special replies if that fits better."""
MAX_ERROR_CHARS = 500       # o erro do Postgres vai para o prompt: limita o tamanho


def generate_sql(question: str, history: list[tuple[str, str]] | None = None,
                 failed: tuple[str, str] | None = None) -> str:
    """Pede ao LLM um SELECT (ou FORECAST / ORDERS / NO_SQL), sempre com ``temperature=0``.

    Args:
        question: Pergunta actual.
        history: Trocas anteriores ``(pergunta, SQL|etiqueta)`` para follow-ups.
        failed: ``(sql, erro)`` de uma tentativa que falhou: o SQL volta como a resposta
            anterior do modelo e o erro como pedido de correção. Os exemplos RAG continuam
            a ser procurados pela pergunta (não pelo texto do erro).

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
    if failed:
        failed_sql, error = failed
        messages.append({"role": "assistant", "content": failed_sql})
        messages.append({"role": "user", "content": FIX_PROMPT.format(error=str(error)[:MAX_ERROR_CHARS])})
    response = client.chat.completions.create(model=MODEL, messages=messages, temperature=0)
    record_llm(response)
    text = response.choices[0].message.content or ""
    # Remove ```sql ... ``` se o modelo as tiver posto; tira o ; final
    return re.sub(r"```(?:sql)?", "", text).strip().rstrip(";")


if __name__ == "__main__":
    print(generate_sql("Qual foi a faturação de cada marca em outubro de 2026?"))
