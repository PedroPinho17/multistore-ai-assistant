-- Role só de leitura usado para correr o SQL gerado pelo LLM.
-- Migração repetível: volta a correr sempre que este ficheiro muda. É autossuficiente:
-- pode correr sozinho e nunca deixa o 'assistente' ler tabelas privadas ou dados pessoais.
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'assistente') THEN
    -- A password é definida por set_passwords.py a partir de READONLY_DATABASE_URL
    CREATE ROLE assistente LOGIN;
  END IF;
END $$;

GRANT CONNECT ON DATABASE multistore TO assistente;
GRANT USAGE ON SCHEMA public TO assistente;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO assistente;

-- Tabelas novas NÃO ficam legíveis automaticamente: cada uma tem de ter o seu
-- GRANT explícito (as vistas em R__profitability.sql e sql_examples em V003__examples.sql têm).
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE SELECT ON TABLES FROM assistente;

-- Tabelas privadas: sem acesso, existam já ou não
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['users', 'app_secret', 'conversations', 'messages', 'setup_steps', 'request_log',
                           'user_settings', 'app_settings', 'schema_migrations', 'query_cache'] LOOP
    IF to_regclass('public.' || t) IS NOT NULL THEN
      EXECUTE format('REVOKE ALL ON %I FROM assistente', t);
    END IF;
  END LOOP;
END $$;

-- RGPD: o GRANT acima dá a tabela employees inteira; aqui fica só com as colunas permitidas
REVOKE SELECT ON employees FROM assistente;
GRANT SELECT (id, store_id, warehouse_id, full_name, role, contract_type, hourly_rate, hired_at)
  ON employees TO assistente;

ALTER ROLE assistente SET default_transaction_read_only = on;
ALTER ROLE assistente SET statement_timeout = '10s';
