-- Utilizadores da aplicação (o assistente NÃO pode ler esta tabela)
CREATE TABLE IF NOT EXISTS users (
  id            serial PRIMARY KEY,
  username      text UNIQUE NOT NULL,
  password_hash text,
  role          text NOT NULL CHECK (role IN ('imperador', 'marca', 'loja')),
  brand_id      int REFERENCES brands(id),
  store_id      int REFERENCES stores(id)
);
REVOKE ALL ON users FROM assistente;

INSERT INTO users (username, role, brand_id, store_id) VALUES
  ('pedro', 'imperador', NULL, NULL),
  ('gestor.burgerlab', 'marca', (SELECT id FROM brands WHERE name = 'BurgerLab'), NULL),
  ('gerente.maia', 'loja', NULL, (SELECT id FROM stores WHERE name = 'BurgerLab Maia'))
ON CONFLICT (username) DO NOTHING;

-- Contexto assinado: a app define app.role / app.brand_id / app.store_id e uma
-- assinatura HMAC (app.sig). Sem a chave secreta, o SQL gerado pelo LLM não
-- consegue fazer-se passar por outro perfil com set_config().
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS app_secret (
  id  int PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  key text NOT NULL
);
INSERT INTO app_secret (key) VALUES (encode(gen_random_bytes(32), 'hex'))
ON CONFLICT (id) DO NOTHING;
REVOKE ALL ON app_secret FROM PUBLIC, assistente;

-- Devolve o perfil só se a assinatura for válida (senão NULL = não vê nada)
CREATE OR REPLACE FUNCTION ctx_role() RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT CASE
    WHEN current_setting('app.sig', true) = encode(hmac(
           coalesce(current_setting('app.role', true), '') || '|' ||
           coalesce(current_setting('app.brand_id', true), '') || '|' ||
           coalesce(current_setting('app.store_id', true), ''),
           (SELECT key FROM app_secret), 'sha256'), 'hex')
    THEN current_setting('app.role', true)
  END
$$;

CREATE OR REPLACE FUNCTION is_imperador() RETURNS boolean
LANGUAGE sql STABLE AS $$
  SELECT coalesce(ctx_role() = 'imperador', false)
$$;

-- Lojas visíveis para o pedido atual (calculado uma vez por query)
CREATE OR REPLACE FUNCTION visible_store_ids() RETURNS int[]
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT coalesce(CASE ctx_role()
    WHEN 'imperador' THEN (SELECT array_agg(id) FROM stores)
    WHEN 'marca' THEN (SELECT array_agg(id) FROM stores
                       WHERE brand_id = nullif(current_setting('app.brand_id', true), '')::int)
    WHEN 'loja' THEN ARRAY[nullif(current_setting('app.store_id', true), '')::int]
  END, ARRAY[]::int[])
$$;

-- Marcas visíveis: imperador todas; marca a sua; loja a marca da sua loja
CREATE OR REPLACE FUNCTION visible_brand_ids() RETURNS int[]
LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT coalesce(CASE ctx_role()
    WHEN 'imperador' THEN (SELECT array_agg(id) FROM brands)
    WHEN 'marca' THEN ARRAY[nullif(current_setting('app.brand_id', true), '')::int]
    WHEN 'loja' THEN (SELECT array_agg(brand_id) FROM stores
                      WHERE id = nullif(current_setting('app.store_id', true), '')::int)
  END, ARRAY[]::int[])
$$;

CREATE OR REPLACE FUNCTION can_see_store(p_store_id int) RETURNS boolean
LANGUAGE sql STABLE AS $$
  SELECT p_store_id = ANY (visible_store_ids())
$$;

-- Ativar RLS e criar as políticas.
-- "(SELECT f())" faz o Postgres calcular a função uma só vez (InitPlan), não por linha.
ALTER TABLE stores         ENABLE ROW LEVEL SECURITY;
ALTER TABLE sales          ENABLE ROW LEVEL SECURITY;
ALTER TABLE sale_lines     ENABLE ROW LEVEL SECURITY;
ALTER TABLE stock          ENABLE ROW LEVEL SECURITY;
ALTER TABLE employees      ENABLE ROW LEVEL SECURITY;
ALTER TABLE shifts         ENABLE ROW LEVEL SECURITY;
ALTER TABLE transfers      ENABLE ROW LEVEL SECURITY;
ALTER TABLE transfer_lines ENABLE ROW LEVEL SECURITY;
ALTER TABLE purchases      ENABLE ROW LEVEL SECURITY;
ALTER TABLE purchase_lines ENABLE ROW LEVEL SECURITY;
ALTER TABLE suppliers      ENABLE ROW LEVEL SECURITY;
-- Catálogo por marca: preços, receitas e margens não passam para as outras marcas
-- (as vistas product_margins, menu_margins e price_recommendations usam
-- security_invoker, por isso herdam estas políticas)
ALTER TABLE products       ENABLE ROW LEVEL SECURITY;
ALTER TABLE menus          ENABLE ROW LEVEL SECURITY;
ALTER TABLE recipes        ENABLE ROW LEVEL SECURITY;
ALTER TABLE menu_items     ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS p_read ON stores;
CREATE POLICY p_read ON stores FOR SELECT USING (id = ANY ((SELECT visible_store_ids())::int[]));

DROP POLICY IF EXISTS p_read ON sales;
CREATE POLICY p_read ON sales FOR SELECT USING (store_id = ANY ((SELECT visible_store_ids())::int[]));

DROP POLICY IF EXISTS p_read ON sale_lines;
CREATE POLICY p_read ON sale_lines FOR SELECT
  USING ((SELECT is_imperador()) OR EXISTS (SELECT 1 FROM sales s WHERE s.id = sale_id));

DROP POLICY IF EXISTS p_read ON stock;
CREATE POLICY p_read ON stock FOR SELECT
  USING ((store_id IS NOT NULL AND store_id = ANY ((SELECT visible_store_ids())::int[]))
      OR (warehouse_id IS NOT NULL AND (SELECT is_imperador())));

DROP POLICY IF EXISTS p_read ON employees;
CREATE POLICY p_read ON employees FOR SELECT
  USING ((store_id IS NOT NULL AND store_id = ANY ((SELECT visible_store_ids())::int[]))
      OR (warehouse_id IS NOT NULL AND (SELECT is_imperador())));

DROP POLICY IF EXISTS p_read ON shifts;
CREATE POLICY p_read ON shifts FOR SELECT
  USING ((SELECT is_imperador()) OR EXISTS (SELECT 1 FROM employees e WHERE e.id = employee_id));

DROP POLICY IF EXISTS p_read ON transfers;
CREATE POLICY p_read ON transfers FOR SELECT USING (store_id = ANY ((SELECT visible_store_ids())::int[]));

DROP POLICY IF EXISTS p_read ON transfer_lines;
CREATE POLICY p_read ON transfer_lines FOR SELECT
  USING ((SELECT is_imperador()) OR EXISTS (SELECT 1 FROM transfers t WHERE t.id = transfer_id));

-- Compras e fornecedores: só o Imperador
DROP POLICY IF EXISTS p_read ON purchases;
CREATE POLICY p_read ON purchases FOR SELECT USING ((SELECT is_imperador()));

DROP POLICY IF EXISTS p_read ON purchase_lines;
CREATE POLICY p_read ON purchase_lines FOR SELECT USING ((SELECT is_imperador()));

DROP POLICY IF EXISTS p_read ON suppliers;
CREATE POLICY p_read ON suppliers FOR SELECT USING ((SELECT is_imperador()));

-- Produtos, menus e receitas: só da(s) marca(s) visível(eis)
DROP POLICY IF EXISTS p_read ON products;
CREATE POLICY p_read ON products FOR SELECT USING (brand_id = ANY ((SELECT visible_brand_ids())::int[]));

DROP POLICY IF EXISTS p_read ON menus;
CREATE POLICY p_read ON menus FOR SELECT USING (brand_id = ANY ((SELECT visible_brand_ids())::int[]));

DROP POLICY IF EXISTS p_read ON recipes;
CREATE POLICY p_read ON recipes FOR SELECT
  USING ((SELECT is_imperador()) OR EXISTS (SELECT 1 FROM products p WHERE p.id = product_id));

DROP POLICY IF EXISTS p_read ON menu_items;
CREATE POLICY p_read ON menu_items FOR SELECT
  USING ((SELECT is_imperador()) OR EXISTS (SELECT 1 FROM menus m WHERE m.id = menu_id));

-- RGPD: o assistente não pode ler dados pessoais sensíveis
REVOKE SELECT ON employees FROM assistente;
GRANT SELECT (id, store_id, warehouse_id, full_name, role, contract_type, hourly_rate, hired_at)
  ON employees TO assistente;