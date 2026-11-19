-- Marcas, lojas e armazéns
CREATE TABLE brands (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  segment TEXT NOT NULL            -- hamburgueria, café, geladaria
);

CREATE TABLE stores (
  id SERIAL PRIMARY KEY,
  brand_id INT NOT NULL REFERENCES brands(id),
  name TEXT NOT NULL,
  city TEXT NOT NULL,
  district TEXT NOT NULL,
  store_type TEXT NOT NULL CHECK (store_type IN ('loja', 'quiosque')),
  opened_at DATE NOT NULL
);

CREATE TABLE warehouses (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  city TEXT NOT NULL
);

-- Trabalhadores e turnos
CREATE TABLE employees (
  id SERIAL PRIMARY KEY,
  store_id INT REFERENCES stores(id),
  warehouse_id INT REFERENCES warehouses(id),
  full_name TEXT NOT NULL,
  birth_date DATE NOT NULL,
  nif CHAR(9) NOT NULL UNIQUE,
  niss CHAR(11) NOT NULL UNIQUE,
  address TEXT NOT NULL,
  role TEXT NOT NULL,              -- gerente, operador, cozinheiro, armazém...
  contract_type TEXT NOT NULL,     -- sem termo, termo certo, part-time
  hourly_rate NUMERIC(6,2) NOT NULL,
  hired_at DATE NOT NULL,
  CHECK ((store_id IS NULL) <> (warehouse_id IS NULL))
);

CREATE TABLE shifts (
  id SERIAL PRIMARY KEY,
  employee_id INT NOT NULL REFERENCES employees(id),
  shift_date DATE NOT NULL,
  start_time TIME NOT NULL,
  end_time TIME NOT NULL
);

-- Ingredientes, produtos, receitas e menus
CREATE TABLE ingredients (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  unit TEXT NOT NULL,              -- kg, l, un
  unit_cost NUMERIC(8,3) NOT NULL
);

CREATE TABLE products (
  id SERIAL PRIMARY KEY,
  brand_id INT NOT NULL REFERENCES brands(id),
  name TEXT NOT NULL,
  category TEXT NOT NULL,          -- hambúrguer, bebida, sobremesa...
  price NUMERIC(6,2) NOT NULL
);

CREATE TABLE recipes (
  product_id INT NOT NULL REFERENCES products(id),
  ingredient_id INT NOT NULL REFERENCES ingredients(id),
  quantity NUMERIC(8,3) NOT NULL,  -- na unidade do ingrediente
  PRIMARY KEY (product_id, ingredient_id)
);

CREATE TABLE menus (
  id SERIAL PRIMARY KEY,
  brand_id INT NOT NULL REFERENCES brands(id),
  name TEXT NOT NULL,
  price NUMERIC(6,2) NOT NULL
);

CREATE TABLE menu_items (
  menu_id INT NOT NULL REFERENCES menus(id),
  product_id INT NOT NULL REFERENCES products(id),
  quantity INT NOT NULL DEFAULT 1,
  PRIMARY KEY (menu_id, product_id)
);

-- Stock, compras e transferências
CREATE TABLE stock (
  id SERIAL PRIMARY KEY,
  store_id INT REFERENCES stores(id),
  warehouse_id INT REFERENCES warehouses(id),
  ingredient_id INT NOT NULL REFERENCES ingredients(id),
  quantity NUMERIC(10,3) NOT NULL,
  updated_at TIMESTAMP NOT NULL DEFAULT now(),
  CHECK ((store_id IS NULL) <> (warehouse_id IS NULL))
);

CREATE TABLE suppliers (
  id SERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  nif CHAR(9) NOT NULL UNIQUE
);

CREATE TABLE purchases (
  id SERIAL PRIMARY KEY,
  supplier_id INT NOT NULL REFERENCES suppliers(id),
  warehouse_id INT NOT NULL REFERENCES warehouses(id),
  ordered_at DATE NOT NULL,
  status TEXT NOT NULL             -- encomendada, recebida
);

CREATE TABLE purchase_lines (
  purchase_id INT NOT NULL REFERENCES purchases(id),
  ingredient_id INT NOT NULL REFERENCES ingredients(id),
  quantity NUMERIC(10,3) NOT NULL,
  unit_cost NUMERIC(8,3) NOT NULL,
  PRIMARY KEY (purchase_id, ingredient_id)
);

CREATE TABLE transfers (
  id SERIAL PRIMARY KEY,
  warehouse_id INT NOT NULL REFERENCES warehouses(id),
  store_id INT NOT NULL REFERENCES stores(id),
  transfer_date DATE NOT NULL
);

CREATE TABLE transfer_lines (
  transfer_id INT NOT NULL REFERENCES transfers(id),
  ingredient_id INT NOT NULL REFERENCES ingredients(id),
  quantity NUMERIC(10,3) NOT NULL,
  PRIMARY KEY (transfer_id, ingredient_id)
);

-- Vendas
CREATE TABLE sales (
  id SERIAL PRIMARY KEY,
  store_id INT NOT NULL REFERENCES stores(id),
  sold_at TIMESTAMP NOT NULL,
  payment_method TEXT NOT NULL,    -- dinheiro, multibanco, mbway
  total NUMERIC(8,2) NOT NULL
);

CREATE TABLE sale_lines (
  id SERIAL PRIMARY KEY,
  sale_id INT NOT NULL REFERENCES sales(id),
  product_id INT REFERENCES products(id),
  menu_id INT REFERENCES menus(id),
  quantity INT NOT NULL,
  unit_price NUMERIC(6,2) NOT NULL,
  CHECK ((product_id IS NULL) <> (menu_id IS NULL))
);

CREATE INDEX idx_sales_store_date ON sales (store_id, sold_at);