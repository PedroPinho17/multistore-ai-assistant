-- Custo e margem por produto (a partir das receitas)
CREATE OR REPLACE VIEW product_margins WITH (security_invoker = true) AS
SELECT p.id AS product_id,
       p.brand_id,
       p.name,
       p.category,
       p.price,
       round(coalesce(sum(r.quantity * i.unit_cost), 0), 2) AS unit_cost,
       round(p.price - coalesce(sum(r.quantity * i.unit_cost), 0), 2) AS unit_margin,
       round(100 * (p.price - coalesce(sum(r.quantity * i.unit_cost), 0)) / p.price, 1) AS margin_pct
FROM products p
LEFT JOIN recipes r ON r.product_id = p.id
LEFT JOIN ingredients i ON i.id = r.ingredient_id
GROUP BY p.id;

-- Custo e margem por menu (soma dos produtos do menu)
CREATE OR REPLACE VIEW menu_margins WITH (security_invoker = true) AS
SELECT m.id AS menu_id,
       m.brand_id,
       m.name,
       m.price,
       round(sum(mi.quantity * pm.unit_cost), 2) AS unit_cost,
       round(m.price - sum(mi.quantity * pm.unit_cost), 2) AS unit_margin,
       round(100 * (m.price - sum(mi.quantity * pm.unit_cost)) / m.price, 1) AS margin_pct
FROM menus m
JOIN menu_items mi ON mi.menu_id = m.id
JOIN product_margins pm ON pm.product_id = mi.product_id
GROUP BY m.id;

GRANT SELECT ON product_margins, menu_margins TO assistente;

-- Recomendações de preço (engenharia de menu, últimos 90 dias, por marca)
CREATE OR REPLACE VIEW price_recommendations WITH (security_invoker = true) AS
WITH vendas AS (
  SELECT pm.product_id, pm.brand_id, pm.name, pm.category, pm.price,
         pm.unit_cost, pm.unit_margin, pm.margin_pct,
         coalesce(sum(sl.quantity), 0) AS units_sold
  FROM product_margins pm
  LEFT JOIN sale_lines sl ON sl.product_id = pm.product_id
  LEFT JOIN sales s ON s.id = sl.sale_id
       AND s.sold_at >= current_date - INTERVAL '90 days'
  WHERE sl.id IS NULL OR s.id IS NOT NULL
  GROUP BY pm.product_id, pm.brand_id, pm.name, pm.category, pm.price,
           pm.unit_cost, pm.unit_margin, pm.margin_pct
),
medias AS (
  SELECT *,
         avg(units_sold)  OVER (PARTITION BY brand_id) AS avg_units,
         avg(unit_margin) OVER (PARTITION BY brand_id) AS avg_margin
  FROM vendas
)
SELECT product_id, brand_id, name, category, price, unit_cost, unit_margin,
       margin_pct, units_sold,
       CASE
         WHEN units_sold >= avg_units AND unit_margin >= avg_margin THEN 'estrela'
         WHEN units_sold >= avg_units THEN 'burro de carga'
         WHEN unit_margin >= avg_margin THEN 'enigma'
         ELSE 'cão'
       END AS classification,
       CASE
         WHEN units_sold >= avg_units AND unit_margin >= avg_margin THEN 'manter o preço'
         WHEN units_sold >= avg_units THEN 'subir o preço ou reduzir o custo da receita'
         WHEN unit_margin >= avg_margin THEN 'promover ou dar mais destaque'
         ELSE 'rever ou retirar da carta'
       END AS recommendation
FROM medias;

GRANT SELECT ON price_recommendations TO assistente;