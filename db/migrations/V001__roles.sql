-- Role só de leitura usado para correr o SQL gerado pelo LLM.
-- A password é definida por data/set_passwords.py a partir de READONLY_DATABASE_URL.
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'assistente') THEN
    -- A password é definida por set_passwords.py a partir de READONLY_DATABASE_URL
    CREATE ROLE assistente LOGIN;
  END IF;
END $$;
