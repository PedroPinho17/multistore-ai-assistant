"""Gera atividade: vendas, turnos, transferências, compras e stock (parte 2).

Simula operação diária com sazonalidade (gelados no verão, etc.), pesos por
dia da semana e janelas horárias por tipo de loja. Depende dos dados base já
inseridos por ``generate.py``.

Uso:
    python -m multistore_ai_assistant.data.generate_activity            # tudo de novo
    python -m multistore_ai_assistant.data.generate_activity --extend   # só os dias em falta

A geração completa cria o histórico base (1 jan 2025 a 16 nov 2026, sempre
igual graças à semente fixa) e depois estende até ontem. ``--extend`` acrescenta
apenas os dias entre a última venda e ontem, sem tocar no histórico: assim
"este mês" ou "ontem" têm sempre dados e a previsão parte de hoje.
"""
import math
import os
import random
import sys
from collections import defaultdict
from datetime import date, datetime, time, timedelta

import psycopg
from dotenv import load_dotenv

from multistore_ai_assistant.data.signals import holiday_factor, weather_factor

load_dotenv()

START = date(2025, 1, 1)
BASE_END = date(2026, 11, 16)   # fim do histórico base (reprodutível)

BASE_TICKETS = {"hamburgueria": 70, "café": 90, "geladaria": 45}
# fator por dia da semana (segunda ... domingo)
WEEKDAY = {
    "hamburgueria": [0.8, 0.8, 0.85, 0.9, 1.15, 1.4, 1.3],
    "café": [1.05, 1.0, 1.0, 1.0, 1.05, 0.95, 0.85],
    "geladaria": [0.8, 0.8, 0.85, 0.9, 1.0, 1.4, 1.45],
}
# janelas de horas (início, fim, peso)
HOURS = {
    "hamburgueria": [(12, 14, 0.5), (19, 22, 0.4), (15, 18, 0.1)],
    "café": [(7, 11, 0.55), (15, 18, 0.35), (12, 14, 0.1)],
    "geladaria": [(13, 17, 0.5), (17, 21, 0.5)],
}
SHIFTS = {
    "hamburgueria": [(time(11), time(16)), (time(18), time(23))],
    "café": [(time(7), time(15)), (time(13), time(20))],
    "geladaria": [(time(12), time(20))],
}
CLOSED = {(12, 25), (1, 1)}
REGION_WAREHOUSE = {"Porto": "Armazém Norte", "Braga": "Armazém Norte", "Aveiro": "Armazém Norte",
                    "Coimbra": "Armazém Centro", "Lisboa": "Armazém Sul", "Faro": "Armazém Sul"}
PAYMENTS, PAYMENT_WEIGHTS = ["multibanco", "mbway", "dinheiro"], [55, 25, 20]


def yesterday() -> date:
    """Último dia completo (as vendas de hoje ainda não fecharam)."""
    return date.today() - timedelta(days=1)


def days(start: date, end: date):
    """Dias de calendário entre ``start`` e ``end``, excluindo Natal e Ano Novo."""
    d = start
    while d <= end:
        if (d.month, d.day) not in CLOSED:
            yield d
        d += timedelta(days=1)


def season(segment: str, d: date) -> float:
    """Multiplicador sazonal (~1 no pico de verão para geladaria)."""
    summer = math.cos(2 * math.pi * (d.timetuple().tm_yday - 200) / 365)  # 1 em julho, -1 em janeiro
    return {"geladaria": 1 + 0.4 * summer, "hamburgueria": 1 + 0.12 * summer}.get(segment, 1 - 0.08 * summer)


def ticket_time(segment: str, d: date) -> datetime:
    """Hora aleatória do talão dentro das janelas típicas do segmento."""
    start, end, _ = random.choices(HOURS[segment], weights=[w for *_, w in HOURS[segment]])[0]
    return datetime.combine(d, time(random.randrange(start, end), random.randrange(60), random.randrange(60)))


def week_start(d: date) -> date:
    """Segunda-feira da semana de ``d``."""
    return d - timedelta(days=d.weekday())


def load_context(cur) -> dict:
    """Lojas, catálogo, receitas, armazéns e fornecedores (dados base)."""
    ctx = {}
    cur.execute("SELECT s.id, s.brand_id, s.district, b.segment FROM stores s JOIN brands b ON b.id = s.brand_id")
    ctx["stores"] = cur.fetchall()
    cur.execute("SELECT id, name FROM warehouses")
    warehouse_by_name = {name: wid for wid, name in cur.fetchall()}
    ctx["store_warehouse"] = {sid: warehouse_by_name[REGION_WAREHOUSE[district]]
                              for sid, _, district, _ in ctx["stores"]}
    cur.execute("SELECT id, unit_cost FROM ingredients")
    ctx["ing_cost"] = {i: float(c) for i, c in cur.fetchall()}
    cur.execute("SELECT id FROM suppliers")
    ctx["suppliers"] = [r[0] for r in cur.fetchall()]

    ctx["recipe"] = defaultdict(list)  # produto -> [(ingrediente, quantidade)]
    cur.execute("SELECT product_id, ingredient_id, quantity FROM recipes")
    for pid, iid, qty in cur.fetchall():
        ctx["recipe"][pid].append((iid, float(qty)))
    ctx["menu_products"] = defaultdict(list)
    cur.execute("SELECT menu_id, product_id FROM menu_items")
    for mid, pid in cur.fetchall():
        ctx["menu_products"][mid].append(pid)

    ctx["catalog"] = defaultdict(list)  # marca -> [(tipo, id, preço, peso)]
    cur.execute("SELECT id, brand_id, price FROM products")
    for pid, bid, price in cur.fetchall():
        ctx["catalog"][bid].append(("p", pid, float(price), 1))
    cur.execute("SELECT id, brand_id, price FROM menus")
    for mid, bid, price in cur.fetchall():
        ctx["catalog"][bid].append(("m", mid, float(price), 3))
    return ctx


def simulate(cur, ctx: dict, start: date, end: date) -> dict:
    """Vendas e turnos de ``start`` a ``end``; devolve o consumo de ingredientes.

    Consumo: (loja, semana, ingrediente) -> quantidade.
    """
    cur.execute("SELECT coalesce(max(id), 0) FROM sales")
    sale_id = cur.fetchone()[0]
    cur.execute("SELECT coalesce(max(id), 0) FROM sale_lines")
    line_id = cur.fetchone()[0]
    consumption = defaultdict(float)

    # --- Vendas ---
    for store_id, brand_id, district, segment in ctx["stores"]:
        sales, lines = [], []
        options = ctx["catalog"][brand_id]
        weights = [o[3] for o in options]
        for d in days(start, end):
            trend = 1 + 0.08 * (d - START).days / 365
            n = (BASE_TICKETS[segment] * WEEKDAY[segment][d.weekday()] * season(segment, d) * trend
                 * weather_factor(segment, district, d) * holiday_factor(segment, district, d))
            for _ in range(max(0, int(random.gauss(n, n * 0.12)))):
                sale_id += 1
                total = 0.0
                for _ in range(random.choices([1, 2, 3, 4], weights=[50, 30, 15, 5])[0]):
                    kind, item_id, price, _ = random.choices(options, weights=weights)[0]
                    qty = 1 if random.random() < 0.9 else 2
                    line_id += 1
                    lines.append((line_id, sale_id, item_id if kind == "p" else None,
                                  item_id if kind == "m" else None, qty, price))
                    total += qty * price
                    for pid in ([item_id] if kind == "p" else ctx["menu_products"][item_id]):
                        for iid, q in ctx["recipe"][pid]:
                            consumption[(store_id, week_start(d), iid)] += q * qty
                sales.append((sale_id, store_id, ticket_time(segment, d),
                              random.choices(PAYMENTS, weights=PAYMENT_WEIGHTS)[0], round(total, 2)))
        with cur.copy("COPY sales (id, store_id, sold_at, payment_method, total) FROM STDIN") as cp:
            for row in sales:
                cp.write_row(row)
        with cur.copy("COPY sale_lines (id, sale_id, product_id, menu_id, quantity, unit_price) FROM STDIN") as cp:
            for row in lines:
                cp.write_row(row)
        print(f"Loja {store_id}: {len(sales)} vendas")

    # --- Turnos ---
    cur.execute("""SELECT e.id, e.store_id, b.segment FROM employees e
                   LEFT JOIN stores s ON s.id = e.store_id LEFT JOIN brands b ON b.id = s.brand_id""")
    employees = cur.fetchall()
    with cur.copy("COPY shifts (employee_id, shift_date, start_time, end_time) FROM STDIN") as cp:
        for emp_id, store_id, segment in employees:
            for d in days(start, end):
                if (d.weekday() + emp_id) % 7 >= 5:  # 2 folgas por semana
                    continue
                s_time, e_time = random.choice(SHIFTS[segment]) if store_id else (time(8), time(16))
                cp.write_row((emp_id, d, s_time, e_time))

    for table in ("sales", "sale_lines"):
        cur.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), (SELECT max(id) FROM {table}))")
    return consumption


def write_supply(cur, ctx: dict, consumption: dict) -> None:
    """Transferências (armazém -> loja) e compras (fornecedor -> armazém).

    Se já existir a transferência/compra dessa semana (extensão a meio da
    semana), soma as quantidades em vez de criar outra.
    """
    per_transfer = defaultdict(dict)
    for (store_id, week, iid), qty in consumption.items():
        per_transfer[(store_id, week)][iid] = qty
    warehouse_week = defaultdict(float)  # (armazém, semana, ingrediente) -> quantidade
    for (store_id, week), items in sorted(per_transfer.items(), key=lambda x: x[0][1]):
        wid = ctx["store_warehouse"][store_id]
        cur.execute("SELECT id FROM transfers WHERE store_id = %s AND transfer_date = %s", (store_id, week))
        row = cur.fetchone()
        if row:
            tid = row[0]
        else:
            cur.execute("INSERT INTO transfers (warehouse_id, store_id, transfer_date) VALUES (%s, %s, %s) RETURNING id",
                        (wid, store_id, week))
            tid = cur.fetchone()[0]
        rows = []
        for iid, qty in items.items():
            q = round(qty * random.uniform(1.0, 1.08), 3)
            rows.append((tid, iid, q))
            warehouse_week[(wid, week, iid)] += q
        cur.executemany("""INSERT INTO transfer_lines VALUES (%s, %s, %s)
                           ON CONFLICT (transfer_id, ingredient_id)
                           DO UPDATE SET quantity = transfer_lines.quantity + EXCLUDED.quantity""", rows)

    # Compras: uma semana antes da transferência
    per_purchase = defaultdict(dict)
    for (wid, week, iid), qty in warehouse_week.items():
        per_purchase[(wid, week)][iid] = qty
    for (wid, week), items in sorted(per_purchase.items(), key=lambda x: x[0][1]):
        ordered_at = week - timedelta(days=7)
        cur.execute("SELECT id FROM purchases WHERE warehouse_id = %s AND ordered_at = %s", (wid, ordered_at))
        row = cur.fetchone()
        if row:
            pid = row[0]
        else:
            cur.execute("""INSERT INTO purchases (supplier_id, warehouse_id, ordered_at, status)
                           VALUES (%s, %s, %s, 'recebida') RETURNING id""",
                        (random.choice(ctx["suppliers"]), wid, ordered_at))
            pid = cur.fetchone()[0]
        cur.executemany("""INSERT INTO purchase_lines VALUES (%s, %s, %s, %s)
                           ON CONFLICT (purchase_id, ingredient_id)
                           DO UPDATE SET quantity = purchase_lines.quantity + EXCLUDED.quantity""",
                        [(pid, iid, round(q * random.uniform(1.0, 1.05), 3),
                          round(ctx["ing_cost"][iid] * random.uniform(0.95, 1.08), 3)) for iid, q in items.items()])

    # Só as compras da semana mais recente estão ainda "encomendadas"
    cur.execute("""UPDATE purchases SET status = CASE WHEN ordered_at >= (SELECT max(ordered_at) FROM purchases)
                                                     THEN 'encomendada' ELSE 'recebida' END""")


def write_stock(cur, end: date) -> None:
    """Stock atual a partir da última semana de transferências e compras."""
    now = datetime.combine(end, time(22))
    cur.execute("DELETE FROM stock")
    cur.execute("""SELECT t.store_id, tl.ingredient_id, tl.quantity FROM transfers t
                   JOIN transfer_lines tl ON tl.transfer_id = t.id
                   WHERE t.transfer_date = (SELECT max(transfer_date) FROM transfers t2 WHERE t2.store_id = t.store_id)
                   ORDER BY 1, 2""")
    for store_id, iid, qty in cur.fetchall():  # algumas lojas ficam com pouco stock
        cur.execute("INSERT INTO stock (store_id, ingredient_id, quantity, updated_at) VALUES (%s, %s, %s, %s)",
                    (store_id, iid, round(float(qty) * random.uniform(0.1, 0.6), 3), now))
    cur.execute("""SELECT p.warehouse_id, pl.ingredient_id, pl.quantity FROM purchases p
                   JOIN purchase_lines pl ON pl.purchase_id = p.id
                   WHERE p.ordered_at = (SELECT max(ordered_at) FROM purchases p2 WHERE p2.warehouse_id = p.warehouse_id)
                   ORDER BY 1, 2""")
    for wid, iid, qty in cur.fetchall():
        cur.execute("INSERT INTO stock (warehouse_id, ingredient_id, quantity, updated_at) VALUES (%s, %s, %s, %s)",
                    (wid, iid, round(float(qty) * random.uniform(0.3, 0.8), 3), now))


def generate_range(cur, start: date, end: date) -> None:
    """Gera toda a atividade de ``start`` a ``end`` (inclusive)."""
    ctx = load_context(cur)
    consumption = simulate(cur, ctx, start, end)
    write_supply(cur, ctx, consumption)
    write_stock(cur, end)


def last_sale_day(cur) -> date | None:
    cur.execute("SELECT max(sold_at)::date FROM sales")
    return cur.fetchone()[0]


def extend(cur, until: date | None = None) -> int:
    """Acrescenta os dias entre a última venda e ``until`` (ontem). Devolve nº de dias."""
    until = until or yesterday()
    last = last_sale_day(cur)
    if last is None:
        raise RuntimeError("Não há vendas: corre primeiro a geração completa (sem --extend).")
    if last >= until:
        print(f"Dados já atualizados (última venda: {last}).")
        return 0
    start = last + timedelta(days=1)
    random.seed(f"extend:{start}:{until}")
    generate_range(cur, start, until)
    print(f"Acrescentados {(until - last).days} dia(s): {start} a {until}.")
    return (until - last).days


def main(only_extend: bool = False) -> None:
    """Geração completa (histórico base + extensão até ontem) ou só a extensão."""
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn, conn.cursor() as cur:
        if not only_extend:
            cur.execute("""TRUNCATE shifts, stock, purchases, purchase_lines, transfers, transfer_lines,
                           sales, sale_lines RESTART IDENTITY""")
            random.seed(7)   # histórico base sempre igual
            generate_range(cur, START, min(BASE_END, yesterday()))
        extend(cur)
        cur.execute("SELECT count(*), min(sold_at)::date, max(sold_at)::date FROM sales")
        n, first, last = cur.fetchone()
        print(f"Feito: {n} vendas de {first} a {last}.")


if __name__ == "__main__":
    main(only_extend="--extend" in sys.argv[1:])
