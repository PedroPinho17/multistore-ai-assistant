"""Exemplos iniciais validados para o RAG (pergunta → SQL).

Corre uma vez após a BD estar pronta: grava embeddings em ``sql_examples``.
"""
from multistore_ai_assistant.assistant.examples import add_example

EXAMPLES = [
    ("Qual foi a faturação de cada marca em outubro de 2026?",
     """SELECT b.name AS marca, ROUND(SUM(s.total), 2) AS faturacao
FROM sales s JOIN stores st ON st.id = s.store_id JOIN brands b ON b.id = st.brand_id
WHERE s.sold_at >= DATE '2026-10-01' AND s.sold_at < DATE '2026-11-01'
GROUP BY b.name ORDER BY faturacao DESC"""),

    ("Quantos gelados vendeu cada loja em agosto de 2026?",
     """WITH linhas AS (
  SELECT sl.sale_id, sl.quantity AS qtd
  FROM sale_lines sl JOIN products p ON p.id = sl.product_id
  WHERE p.category = 'gelado'
  UNION ALL
  SELECT sl.sale_id, sl.quantity * mi.quantity
  FROM sale_lines sl JOIN menu_items mi ON mi.menu_id = sl.menu_id
  JOIN products p ON p.id = mi.product_id
  WHERE p.category = 'gelado'
)
SELECT st.name AS loja, SUM(l.qtd) AS gelados
FROM linhas l JOIN sales s ON s.id = l.sale_id JOIN stores st ON st.id = s.store_id
WHERE s.sold_at >= DATE '2026-08-01' AND s.sold_at < DATE '2026-09-01'
GROUP BY st.name ORDER BY gelados DESC"""),

    ("Qual o talão médio por marca em 2026?",
     """SELECT b.name AS marca, ROUND(AVG(s.total), 2) AS talao_medio, COUNT(*) AS taloes
FROM sales s JOIN stores st ON st.id = s.store_id JOIN brands b ON b.id = st.brand_id
WHERE s.sold_at >= DATE '2026-01-01' AND s.sold_at < DATE '2027-01-01'
GROUP BY b.name ORDER BY talao_medio DESC"""),

    ("Qual a faturação por método de pagamento este mês?",
     """SELECT s.payment_method AS metodo_pagamento, ROUND(SUM(s.total), 2) AS faturacao, COUNT(*) AS taloes
FROM sales s
WHERE s.sold_at >= date_trunc('month', CURRENT_DATE)
GROUP BY s.payment_method ORDER BY faturacao DESC"""),

    ("Quantas horas trabalharam os funcionários de cada loja na semana passada?",
     """SELECT st.name AS loja,
       ROUND(SUM(EXTRACT(EPOCH FROM (sh.end_time - sh.start_time)) / 3600), 1) AS horas
FROM shifts sh JOIN employees e ON e.id = sh.employee_id JOIN stores st ON st.id = e.store_id
WHERE sh.shift_date >= date_trunc('week', CURRENT_DATE) - INTERVAL '7 days'
  AND sh.shift_date <  date_trunc('week', CURRENT_DATE)
GROUP BY st.name ORDER BY horas DESC"""),

    ("Que ingredientes estão com stock mais baixo nas lojas?",
     """SELECT st.name AS loja, i.name AS ingrediente, i.unit AS unidade, s.quantity AS quantidade
FROM stock s JOIN stores st ON st.id = s.store_id JOIN ingredients i ON i.id = s.ingredient_id
WHERE s.store_id IS NOT NULL
ORDER BY s.quantity ASC LIMIT 20"""),

    ("Que compras estão por receber?",
     """SELECT p.id AS compra, su.name AS fornecedor, w.name AS armazem, p.ordered_at AS data_encomenda,
       ROUND(SUM(pl.quantity * pl.unit_cost), 2) AS valor
FROM purchases p JOIN suppliers su ON su.id = p.supplier_id JOIN warehouses w ON w.id = p.warehouse_id
JOIN purchase_lines pl ON pl.purchase_id = p.id
WHERE p.status = 'encomendada'
GROUP BY p.id, su.name, w.name, p.ordered_at ORDER BY p.ordered_at"""),

    ("Quantos menus vendeu cada loja da BurgerLab em 2026?",
     """SELECT st.name AS loja, m.name AS menu, SUM(sl.quantity) AS quantidade
FROM sale_lines sl JOIN menus m ON m.id = sl.menu_id JOIN sales s ON s.id = sl.sale_id
JOIN stores st ON st.id = s.store_id JOIN brands b ON b.id = st.brand_id
WHERE b.name = 'BurgerLab' AND s.sold_at >= DATE '2026-01-01' AND s.sold_at < DATE '2027-01-01'
GROUP BY st.name, m.name ORDER BY st.name, quantidade DESC"""),

    (
        "Quais os produtos com maior margem percentual?",
        """SELECT b.name AS marca, pm.name AS produto, pm.price AS preco,
       pm.unit_cost AS custo, pm.margin_pct AS margem_pct
FROM product_margins pm
JOIN brands b ON b.id = pm.brand_id
ORDER BY pm.margin_pct DESC
LIMIT 10""",
    ),
    (
        "Quais os produtos que deram mais margem total em 2026?",
        """SELECT pm.name AS produto,
       round(sum(sl.quantity * (sl.unit_price - pm.unit_cost)), 2) AS margem_total_euros
FROM sale_lines sl
JOIN sales s ON s.id = sl.sale_id
JOIN product_margins pm ON pm.product_id = sl.product_id
WHERE s.sold_at >= '2026-01-01'
GROUP BY pm.name
ORDER BY margem_total_euros DESC
LIMIT 10""",
    ),
    (
        "Em que produtos devo mexer no preço?",
        """SELECT b.name AS marca, pr.name AS produto, pr.price AS preco,
       pr.margin_pct AS margem_pct, pr.units_sold AS unidades_90_dias,
       pr.classification AS classificacao, pr.recommendation AS recomendacao
FROM price_recommendations pr
JOIN brands b ON b.id = pr.brand_id
ORDER BY b.name, pr.classification""",
    ),
]

if __name__ == "__main__":
    for question, sql in EXAMPLES:
        add_example(question, sql)
        print("OK", question)
