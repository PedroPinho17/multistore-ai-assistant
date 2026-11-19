"""Gera dados fictícios para a base de dados (parte 1: dados base).

Insere marcas, lojas, armazéns, ingredientes, produtos, menus, receitas,
funcionários e utilizadores de demo. A actividade (vendas, stock, …) fica
em ``generate_activity.py``. Tudo é determinístico (seed 42) e em pt_PT.
"""
import os
import random
from datetime import date

import psycopg
from dotenv import load_dotenv
from faker import Faker

load_dotenv()
fake = Faker("pt_PT")
Faker.seed(42)
random.seed(42)

BRANDS = [("BurgerLab", "hamburgueria"), ("Café Aroma", "café"), ("Gelato Mar", "geladaria")]

CITIES = [
    ("Porto", "Porto"), ("Vila Nova de Gaia", "Porto"), ("Matosinhos", "Porto"),
    ("Maia", "Porto"), ("Braga", "Braga"), ("Aveiro", "Aveiro"),
    ("Coimbra", "Coimbra"), ("Lisboa", "Lisboa"), ("Oeiras", "Lisboa"), ("Faro", "Faro"),
]

# marca: (número de lojas, tipo)
STORES_PER_BRAND = {"BurgerLab": (6, "loja"), "Café Aroma": (5, "loja"), "Gelato Mar": (4, "quiosque")}

WAREHOUSES = [("Armazém Norte", "Maia"), ("Armazém Centro", "Coimbra"), ("Armazém Sul", "Lisboa")]

# ingrediente: (unidade, custo por unidade)
INGREDIENTS = {
    "Pão de hambúrguer": ("un", 0.25), "Carne de vaca picada": ("kg", 8.50),
    "Peito de frango": ("kg", 6.20), "Queijo cheddar": ("kg", 9.80),
    "Fiambre": ("kg", 7.20), "Pão de forma": ("un", 0.08),
    "Alface": ("kg", 1.90), "Tomate": ("kg", 1.70), "Cebola": ("kg", 0.90),
    "Bacon": ("kg", 10.50), "Batata palito congelada": ("kg", 1.60),
    "Óleo de fritura": ("l", 2.10), "Molho da casa": ("l", 4.50),
    "Refrigerante (xarope)": ("l", 3.20), "Café em grão": ("kg", 14.00),
    "Leite": ("l", 0.85), "Açúcar": ("kg", 1.10), "Farinha": ("kg", 0.70),
    "Manteiga": ("kg", 7.50), "Ovos": ("un", 0.18), "Natas": ("l", 3.60),
    "Chocolate": ("kg", 9.00), "Morango": ("kg", 4.80), "Limão": ("kg", 1.50),
    "Copo/cone": ("un", 0.05),
}

# produto: (marca, categoria, preço, receita {ingrediente: quantidade})
PRODUCTS = {
    "Lab Classic": ("BurgerLab", "hambúrguer", 7.50, {"Pão de hambúrguer": 1, "Carne de vaca picada": 0.15, "Queijo cheddar": 0.02, "Alface": 0.02, "Tomate": 0.03, "Molho da casa": 0.02}),
    "Lab Bacon": ("BurgerLab", "hambúrguer", 8.90, {"Pão de hambúrguer": 1, "Carne de vaca picada": 0.15, "Queijo cheddar": 0.03, "Bacon": 0.04, "Cebola": 0.02, "Molho da casa": 0.02}),
    "Lab Chicken": ("BurgerLab", "hambúrguer", 7.90, {"Pão de hambúrguer": 1, "Peito de frango": 0.14, "Alface": 0.02, "Tomate": 0.03, "Molho da casa": 0.02}),
    "Batatas fritas": ("BurgerLab", "acompanhamento", 2.50, {"Batata palito congelada": 0.15, "Óleo de fritura": 0.01}),
    "Refrigerante": ("BurgerLab", "bebida", 2.00, {"Refrigerante (xarope)": 0.06, "Copo/cone": 1}),
    "Café expresso": ("Café Aroma", "bebida", 0.80, {"Café em grão": 0.007, "Açúcar": 0.005}),
    "Galão": ("Café Aroma", "bebida", 1.40, {"Café em grão": 0.007, "Leite": 0.2, "Açúcar": 0.005}),
    "Croissant": ("Café Aroma", "pastelaria", 1.30, {"Farinha": 0.05, "Manteiga": 0.02, "Ovos": 0.2}),
    "Pastel de nata": ("Café Aroma", "pastelaria", 1.20, {"Farinha": 0.02, "Leite": 0.04, "Ovos": 0.5, "Açúcar": 0.015, "Natas": 0.02}),
    "Tosta mista": ("Café Aroma", "salgado", 3.20, {"Pão de forma": 2, "Fiambre": 0.03, "Queijo cheddar": 0.03, "Manteiga": 0.01}),
    "Gelado chocolate": ("Gelato Mar", "gelado", 3.00, {"Leite": 0.1, "Natas": 0.04, "Chocolate": 0.03, "Açúcar": 0.02, "Copo/cone": 1}),
    "Gelado morango": ("Gelato Mar", "gelado", 3.00, {"Leite": 0.1, "Natas": 0.04, "Morango": 0.05, "Açúcar": 0.02, "Copo/cone": 1}),
    "Sorvete de limão": ("Gelato Mar", "gelado", 2.80, {"Limão": 0.06, "Açúcar": 0.03, "Copo/cone": 1}),
    "Batido de morango": ("Gelato Mar", "bebida", 3.80, {"Leite": 0.25, "Natas": 0.03, "Morango": 0.05, "Açúcar": 0.02, "Copo/cone": 1}),
}

# menu: (marca, preço, produtos)
MENUS = {
    "Menu Classic": ("BurgerLab", 10.50, ["Lab Classic", "Batatas fritas", "Refrigerante"]),
    "Menu Bacon": ("BurgerLab", 11.90, ["Lab Bacon", "Batatas fritas", "Refrigerante"]),
    "Menu Chicken": ("BurgerLab", 10.90, ["Lab Chicken", "Batatas fritas", "Refrigerante"]),
    "Pequeno-almoço": ("Café Aroma", 2.40, ["Galão", "Croissant"]),
    "Pausa doce": ("Café Aroma", 1.80, ["Café expresso", "Pastel de nata"]),
}

STORE_ROLES = {
    "hamburgueria": ["cozinheiro", "operador de caixa", "operador de sala"],
    "café": ["barista", "pasteleiro", "operador de caixa"],
    "geladaria": ["operador de quiosque"],
}
CONTRACTS = ["sem termo", "termo certo", "part-time"]


def nif(first_digit: str = "2") -> str:
    """NIF português válido (9 dígitos, último é o dígito de controlo)."""
    digits = first_digit + "".join(random.choices("0123456789", k=7))
    total = sum(int(d) * w for d, w in zip(digits, range(9, 1, -1), strict=False))
    check = 11 - total % 11
    return digits + str(0 if check >= 10 else check)


def niss() -> str:
    """NISS português válido (11 dígitos, começa por 1 para pessoas singulares)."""
    digits = "1" + "".join(random.choices("0123456789", k=9))
    weights = [29, 23, 19, 17, 13, 11, 7, 5, 3, 2]
    total = sum(int(d) * w for d, w in zip(digits, weights, strict=False))
    return digits + str(9 - total % 10)


def insert(cur, sql: str, params: tuple) -> int:
    """Executa INSERT … RETURNING id e devolve o id gerado."""
    cur.execute(sql + " RETURNING id", params)
    return cur.fetchone()[0]


def employee(cur, role: str, rate: tuple[float, float], store_id=None, warehouse_id=None):
    """Insere um funcionário fictício numa loja ou num armazém."""
    hired = fake.date_between(date(2018, 1, 1), date(2025, 12, 31))
    cur.execute(
        """INSERT INTO employees (store_id, warehouse_id, full_name, birth_date, nif, niss,
           address, role, contract_type, hourly_rate, hired_at)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (store_id, warehouse_id, fake.name(),
         fake.date_of_birth(minimum_age=18, maximum_age=62),
         nif(random.choice("123")), niss(), fake.address().replace("\n", ", "),
         role, random.choices(CONTRACTS, weights=[5, 3, 2])[0],
         round(random.uniform(*rate), 2), hired),
    )


def main():
    """Apaga dados base e volta a criar marcas, lojas, produtos, menus e staff."""
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn, conn.cursor() as cur:
        cur.execute("""TRUNCATE brands, stores, warehouses, employees, shifts, ingredients,
                       products, recipes, menus, menu_items, stock, suppliers, purchases,
                       purchase_lines, transfers, transfer_lines, sales, sale_lines
                       RESTART IDENTITY CASCADE""")

        brand_ids = {name: insert(cur, "INSERT INTO brands (name, segment) VALUES (%s, %s)", (name, seg))
                     for name, seg in BRANDS}
        segments = dict(BRANDS)

        for name, city in WAREHOUSES:
            wid = insert(cur, "INSERT INTO warehouses (name, city) VALUES (%s, %s)", (name, city))
            employee(cur, "responsável de armazém", (7.5, 9.0), warehouse_id=wid)
            for _ in range(random.randint(2, 4)):
                employee(cur, "operador de armazém", (5.3, 6.5), warehouse_id=wid)

        for brand, (count, store_type) in STORES_PER_BRAND.items():
            for city, district in random.sample(CITIES, count):
                sid = insert(cur,
                    """INSERT INTO stores (brand_id, name, city, district, store_type, opened_at)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (brand_ids[brand], f"{brand} {city}", city, district, store_type,
                     fake.date_between(date(2015, 1, 1), date(2024, 6, 30))))
                employee(cur, "gerente", (7.5, 9.5), store_id=sid)
                for _ in range(random.randint(4, 9) if store_type == "loja" else random.randint(2, 3)):
                    employee(cur, random.choice(STORE_ROLES[segments[brand]]), (5.3, 6.5), store_id=sid)

        ing_ids = {name: insert(cur, "INSERT INTO ingredients (name, unit, unit_cost) VALUES (%s, %s, %s)",
                                (name, unit, cost))
                   for name, (unit, cost) in INGREDIENTS.items()}

        prod_ids = {}
        for name, (brand, category, price, recipe) in PRODUCTS.items():
            pid = insert(cur, "INSERT INTO products (brand_id, name, category, price) VALUES (%s, %s, %s, %s)",
                         (brand_ids[brand], name, category, price))
            prod_ids[name] = pid
            for ing, qty in recipe.items():
                cur.execute("INSERT INTO recipes VALUES (%s, %s, %s)", (pid, ing_ids[ing], qty))

        for name, (brand, price, items) in MENUS.items():
            mid = insert(cur, "INSERT INTO menus (brand_id, name, price) VALUES (%s, %s, %s)",
                         (brand_ids[brand], name, price))
            for item in items:
                cur.execute("INSERT INTO menu_items (menu_id, product_id) VALUES (%s, %s)", (mid, prod_ids[item]))

        for _ in range(6):
            cur.execute("INSERT INTO suppliers (name, nif) VALUES (%s, %s)", (fake.company(), nif("5")))

        cur.execute("SELECT count(*) FROM employees")
        print(f"Dados base criados: {len(BRANDS)} marcas, {sum(c for c, _ in STORES_PER_BRAND.values())} lojas, "
              f"{cur.fetchone()[0]} trabalhadores, {len(PRODUCTS)} produtos, {len(MENUS)} menus.")


if __name__ == "__main__":
    main()
