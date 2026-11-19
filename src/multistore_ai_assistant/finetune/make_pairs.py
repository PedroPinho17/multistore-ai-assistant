"""Gera pares pergunta/SQL verificados na base de dados, para o fine-tune."""
import json
import random
from datetime import date
from itertools import product
from pathlib import Path

from multistore_ai_assistant.db.query import IMPERADOR, run_query

random.seed(42)
PER_TEMPLATE = 15          # combinações por modelo (x2 línguas)
OUT = Path("data/finetune_pairs.jsonl")
EVAL = Path("eval/questions.json")
SPECIAL = {"NO_SQL", "FORECAST", "ORDERS"}

MONTHS_PT = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
             "agosto", "setembro", "outubro", "novembro", "dezembro"]
MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July",
             "August", "September", "October", "November", "December"]

BRAND_SALES = ("FROM sales s JOIN stores st ON st.id = s.store_id "
               "JOIN brands b ON b.id = st.brand_id ")
STORE_SALES = "FROM sales s JOIN stores st ON st.id = s.store_id "
MONTH = "s.sold_at >= '{start}' AND s.sold_at < '{end}'"
YEAR = "s.sold_at >= '{year}-01-01' AND s.sold_at < '{next_year}-01-01'"

TEMPLATES = [
    {"slots": ("brand", "month"),
     "pt": "Qual foi a faturação da {brand} em {month_pt}?",
     "en": "What was {brand}'s revenue in {month_en}?",
     "sql": "SELECT ROUND(SUM(s.total), 2) AS faturacao " + BRAND_SALES
            + "WHERE b.name ILIKE '{brand_sql}' AND " + MONTH},
    {"slots": ("store", "month"),
     "pt": "Quanto faturou a loja {store} em {month_pt}?",
     "en": "How much revenue did the {store} store make in {month_en}?",
     "sql": "SELECT ROUND(SUM(s.total), 2) AS faturacao " + STORE_SALES
            + "WHERE st.name ILIKE '{store_sql}' AND " + MONTH},
    {"slots": ("store", "month"),
     "pt": "Quantas vendas fez a loja {store} em {month_pt}?",
     "en": "How many sales did {store} make in {month_en}?",
     "sql": "SELECT COUNT(s.id) AS numero_vendas " + STORE_SALES
            + "WHERE st.name ILIKE '{store_sql}' AND " + MONTH},
    {"slots": ("brand", "month"),
     "pt": "Qual foi o ticket médio da {brand} em {month_pt}?",
     "en": "What was the average ticket at {brand} in {month_en}?",
     "sql": "SELECT ROUND(AVG(s.total), 2) AS ticket_medio " + BRAND_SALES
            + "WHERE b.name ILIKE '{brand_sql}' AND " + MONTH},
    {"slots": ("store", "method", "month"),
     "pt": "Quanto faturou a loja {store} com pagamentos em {method} em {month_pt}?",
     "en": "How much did {store} take in {method} payments in {month_en}?",
     "sql": "SELECT ROUND(SUM(s.total), 2) AS faturacao " + STORE_SALES
            + "WHERE st.name ILIKE '{store_sql}' AND s.payment_method = '{method_sql}' AND " + MONTH},
    {"slots": ("brand", "year"),
     "pt": "Quais foram os 5 produtos mais vendidos da {brand} em {year}?",
     "en": "What were {brand}'s 5 best-selling products in {year}?",
     "sql": "SELECT p.name AS produto, SUM(sl.quantity) AS quantidade FROM sale_lines sl "
            "JOIN products p ON p.id = sl.product_id JOIN brands b ON b.id = p.brand_id "
            "JOIN sales s ON s.id = sl.sale_id WHERE b.name ILIKE '{brand_sql}' AND " + YEAR
            + " GROUP BY p.name ORDER BY quantidade DESC LIMIT 5"},
    {"slots": ("brand", "year"),
     "pt": "Qual foi a loja da {brand} que mais faturou em {year}?",
     "en": "Which {brand} store had the highest revenue in {year}?",
     "sql": "SELECT st.name AS loja, ROUND(SUM(s.total), 2) AS faturacao " + BRAND_SALES
            + "WHERE b.name ILIKE '{brand_sql}' AND " + YEAR
            + " GROUP BY st.name ORDER BY faturacao DESC LIMIT 1"},
    {"slots": ("brand", "year"),
     "pt": "Mostra a faturação mensal da {brand} em {year}.",
     "en": "Show {brand}'s monthly revenue in {year}.",
     "sql": "SELECT date_trunc('month', s.sold_at)::date AS mes, ROUND(SUM(s.total), 2) AS faturacao "
            + BRAND_SALES + "WHERE b.name ILIKE '{brand_sql}' AND " + YEAR
            + " GROUP BY mes ORDER BY mes"},
    {"slots": ("product", "month"),
     "pt": "Quantas unidades de {product} se venderam em {month_pt}?",
     "en": "How many {product} were sold in {month_en}?",
     "sql": "SELECT SUM(sl.quantity) AS quantidade FROM sale_lines sl "
            "JOIN products p ON p.id = sl.product_id JOIN sales s ON s.id = sl.sale_id "
            "WHERE p.name ILIKE '{product_sql}' AND " + MONTH},
    {"slots": ("product",),
     "pt": "Qual é a margem do produto {product}?",
     "en": "What is the margin of {product}?",
     "sql": "SELECT name AS produto, price AS preco, unit_cost AS custo, unit_margin AS margem, "
            "margin_pct AS margem_pct FROM product_margins WHERE name ILIKE '{product_sql}'"},
    {"slots": ("product",),
     "pt": "Quais são os ingredientes do {product}?",
     "en": "What are the ingredients of {product}?",
     "sql": "SELECT i.name AS ingrediente, r.quantity AS quantidade, i.unit AS unidade "
            "FROM recipes r JOIN products p ON p.id = r.product_id "
            "JOIN ingredients i ON i.id = r.ingredient_id WHERE p.name ILIKE '{product_sql}'"},
    {"slots": ("city",),
     "pt": "Que lojas temos em {city}?",
     "en": "Which stores do we have in {city}?",
     "sql": "SELECT st.name AS loja, b.name AS marca FROM stores st "
            "JOIN brands b ON b.id = st.brand_id WHERE st.city ILIKE '{city_sql}'"},
    {"slots": ("store",),
     "pt": "Quantos funcionários tem a loja {store}?",
     "en": "How many employees does {store} have?",
     "sql": "SELECT COUNT(e.id) AS funcionarios FROM employees e "
            "JOIN stores st ON st.id = e.store_id WHERE st.name ILIKE '{store_sql}'"},
    {"slots": ("store", "month"),
     "pt": "Quantas horas se trabalharam na loja {store} em {month_pt}?",
     "en": "How many hours were worked at {store} in {month_en}?",
     "sql": "SELECT ROUND(SUM(EXTRACT(EPOCH FROM (sh.end_time - sh.start_time)) / 3600), 2) AS horas "
            "FROM shifts sh JOIN employees e ON e.id = sh.employee_id "
            "JOIN stores st ON st.id = e.store_id WHERE st.name ILIKE '{store_sql}' "
            "AND sh.shift_date >= '{start}' AND sh.shift_date < '{end}'"},
    {"slots": ("store", "ingredient"),
     "pt": "Quanto stock de {ingredient} tem a loja {store}?",
     "en": "How much {ingredient} does {store} have in stock?",
     "sql": "SELECT ROUND(SUM(sk.quantity), 3) AS quantidade, i.unit AS unidade FROM stock sk "
            "JOIN ingredients i ON i.id = sk.ingredient_id JOIN stores st ON st.id = sk.store_id "
            "WHERE st.name ILIKE '{store_sql}' AND i.name ILIKE '{ingredient_sql}' GROUP BY i.unit"},
    {"slots": ("warehouse",),
     "pt": "Quantas compras estão por receber no armazém {warehouse}?",
     "en": "How many purchases are still pending at the {warehouse} warehouse?",
     "sql": "SELECT COUNT(p.id) AS compras_por_receber FROM purchases p "
            "JOIN warehouses w ON w.id = p.warehouse_id "
            "WHERE w.name ILIKE '{warehouse_sql}' AND p.status = 'encomendada'"},
    # Respostas especiais (não correm na BD)
    {"slots": ("store",), "sql": "NO_SQL",
     "pt": "Qual é o NIF do gerente da loja {store}?",
     "en": "What is the NIF of the manager at {store}?"},
    {"slots": ("brand",), "sql": "NO_SQL",
     "pt": "Dá-me as moradas dos funcionários da {brand}.",
     "en": "Give me the addresses of {brand}'s employees."},
    {"slots": ("store",), "sql": "NO_SQL",
     "pt": "Apaga as vendas de ontem da loja {store}.",
     "en": "Delete yesterday's sales at {store}."},
    {"slots": ("store",), "sql": "FORECAST",
     "pt": "Quanto vai vender a loja {store} na próxima semana?",
     "en": "How much will {store} sell next week?"},
    {"slots": ("store",), "sql": "ORDERS",
     "pt": "Que ingredientes devo encomendar para a loja {store}?",
     "en": "Which ingredients should I order for {store}?"},
]


def values(sql: str) -> list:
    """Primeira coluna do resultado (lista de valores para preencher slots)."""
    _, rows = run_query(sql, IMPERADOR)
    return [r[0] for r in rows]


def load_slots() -> dict:
    """Valores reais da BD para preencher os templates (marcas, lojas, meses, …)."""
    months = values("SELECT DISTINCT date_trunc('month', sold_at)::date FROM sales ORDER BY 1")
    years = sorted({m.year for m in months})
    return {
        "brand": values("SELECT name FROM brands"),
        # só lojas com nome único (as duas da Maia ficam de fora)
        "store": values("SELECT name FROM stores GROUP BY name HAVING COUNT(*) = 1"),
        "city": values("SELECT DISTINCT city FROM stores"),
        "product": values("SELECT name FROM products"),
        "ingredient": values("SELECT name FROM ingredients"),
        "method": values("SELECT DISTINCT payment_method FROM sales"),
        "warehouse": values("SELECT name FROM warehouses"),
        "month": months[:-1],  # sem o mês atual, que ainda está incompleto
        "year": years,
    }


def fill(name: str, value) -> dict:
    """Expande um slot num dict de chaves para ``str.format`` (PT/EN + SQL)."""
    if name == "month":
        nxt = date(value.year + value.month // 12, value.month % 12 + 1, 1)
        return {"month_pt": f"{MONTHS_PT[value.month - 1]} de {value.year}",
                "month_en": f"{MONTHS_EN[value.month - 1]} {value.year}",
                "start": value.isoformat(), "end": nxt.isoformat()}
    if name == "year":
        return {"year": value, "next_year": value + 1}
    return {name: value, f"{name}_sql": str(value).replace("'", "''")}


def has_data(sql: str) -> bool:
    """True se a query corre e devolve pelo menos uma célula não-nula."""
    try:
        _, rows = run_query(sql, IMPERADOR)
    except Exception as e:
        print("  ERRO:", e, "\n  ", sql)
        return False
    return bool(rows) and any(v is not None for v in rows[0])


def main():
    """Gera ``data/finetune_pairs.jsonl`` (exclui perguntas já no eval)."""
    slots = load_slots()
    eval_items = json.loads(EVAL.read_text(encoding="utf-8"))
    seen = {item["q"].strip().lower() for item in eval_items}
    pairs = []

    for t in TEMPLATES:
        combos = list(product(*(slots[s] for s in t["slots"])))
        random.shuffle(combos)
        kept = 0
        for combo in combos[: PER_TEMPLATE * 4]:
            if kept == PER_TEMPLATE:
                break
            keys = {}
            for name, value in zip(t["slots"], combo, strict=False):
                keys.update(fill(name, value))
            sql = t["sql"].format(**keys)
            if sql not in SPECIAL and not has_data(sql):
                continue
            for lang in ("pt", "en"):
                question = t[lang].format(**keys)
                if question.strip().lower() in seen:
                    continue
                seen.add(question.strip().lower())
                pairs.append({"question": question, "sql": sql, "lang": lang})
            kept += 1
        print(f"{t['pt'][:55]:55} -> {kept}")

    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for p in pairs:
            f.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"\n{len(pairs)} pares guardados em {OUT}")


if __name__ == "__main__":
    main()
