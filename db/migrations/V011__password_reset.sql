-- Recuperação de password por email ("Esqueceu-se da password?").
-- O token só existe no link enviado por email; aqui fica o SHA-256 dele, a validade
-- e quando foi usado (uso único). As contas de demonstração não têm email: a password
-- delas é pública, por isso não se recupera (nem se muda).

ALTER TABLE users ADD COLUMN IF NOT EXISTS email text;

ALTER TABLE users DROP CONSTRAINT IF EXISTS users_email_check;
ALTER TABLE users ADD CONSTRAINT users_email_check
  CHECK (email IS NULL OR (length(email) <= 254 AND email ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$'));

ALTER TABLE users DROP CONSTRAINT IF EXISTS users_demo_no_email;
ALTER TABLE users ADD CONSTRAINT users_demo_no_email
  CHECK (email IS NULL OR NOT protected OR role = 'admin');

-- Um email por conta (sem distinguir maiúsculas)
CREATE UNIQUE INDEX IF NOT EXISTS users_email_key ON users (lower(email));

CREATE TABLE IF NOT EXISTS password_resets (
  id           serial PRIMARY KEY,
  user_id      int NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash   text NOT NULL UNIQUE CHECK (token_hash ~ '^[0-9a-f]{64}$'),
  created_at   timestamptz NOT NULL DEFAULT now(),
  expires_at   timestamptz NOT NULL,
  used_at      timestamptz,
  requested_ip text
);
CREATE INDEX IF NOT EXISTS idx_password_resets_user ON password_resets (user_id, created_at DESC);

-- Privada: o assistente (SQL do LLM) nunca a lê
REVOKE ALL ON password_resets FROM PUBLIC;
DO $$
BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'assistente') THEN
    REVOKE ALL ON password_resets FROM assistente;
  END IF;
END $$;
