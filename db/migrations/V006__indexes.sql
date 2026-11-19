-- migrate: no-transaction
-- (REINDEX DATABASE não corre dentro de uma transação)
CREATE INDEX IF NOT EXISTS idx_sale_lines_sale    ON sale_lines (sale_id);
CREATE INDEX IF NOT EXISTS idx_sale_lines_product ON sale_lines (product_id);
CREATE INDEX IF NOT EXISTS idx_sale_lines_menu    ON sale_lines (menu_id);
CREATE INDEX IF NOT EXISTS idx_sales_sold_at      ON sales (sold_at);
CREATE INDEX IF NOT EXISTS idx_shifts_employee    ON shifts (employee_id, shift_date);
CREATE INDEX IF NOT EXISTS idx_employees_store    ON employees (store_id);
CREATE INDEX IF NOT EXISTS idx_stock_store        ON stock (store_id);
CREATE INDEX IF NOT EXISTS idx_transfers_store    ON transfers (store_id, transfer_date);
ANALYZE;

REINDEX DATABASE multistore;
ALTER DATABASE multistore REFRESH COLLATION VERSION;