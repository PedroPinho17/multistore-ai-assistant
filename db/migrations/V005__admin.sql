-- Perfis, módulos, gestão de utilizadores e observabilidade.
-- Idempotente: corre depois de V002__security.sql e V004__conversations.sql.

-- ---------- Utilizadores: perfil admin, módulos e estado ----------
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
ALTER TABLE users ADD CONSTRAINT users_role_check
  CHECK (role IN ('admin', 'imperador', 'marca', 'loja'));

ALTER TABLE users ADD COLUMN IF NOT EXISTS modules    text[];      -- NULL = módulos por defeito do perfil
ALTER TABLE users ADD COLUMN IF NOT EXISTS active     boolean NOT NULL DEFAULT true;
ALTER TABLE users ADD COLUMN IF NOT EXISTS protected  boolean NOT NULL DEFAULT false;  -- contas de demo
ALTER TABLE users ADD COLUMN IF NOT EXISTS created_by int REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now();
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login timestamptz;
-- Foto de perfil: data URL pequeno (a UI envia 160×160 WebP); o Python valida o conteúdo
ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar text;
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_avatar_check;
ALTER TABLE users ADD CONSTRAINT users_avatar_check CHECK (
  avatar IS NULL OR (length(avatar) <= 100000 AND avatar ~ '^data:image/(png|jpeg|webp);base64,'));

-- O âmbito tem de bater com o perfil (uma conta de loja não pode ficar sem loja)
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_scope_check;
ALTER TABLE users ADD CONSTRAINT users_scope_check CHECK (
  (role IN ('admin', 'imperador') AND brand_id IS NULL AND store_id IS NULL)
  OR (role = 'marca' AND brand_id IS NOT NULL AND store_id IS NULL)
  OR (role = 'loja'  AND store_id IS NOT NULL AND brand_id IS NULL));

ALTER TABLE users DROP CONSTRAINT IF EXISTS users_username_check;
ALTER TABLE users ADD CONSTRAINT users_username_check CHECK (username ~ '^[a-z0-9._-]{3,32}$');

-- As 3 contas públicas de demonstração: ninguém as altera nem apaga pela app (só o admin)
UPDATE users SET protected = true
WHERE username IN ('pedro', 'gestor.burgerlab', 'gerente.maia') AND NOT protected;

-- ---------- Observabilidade: um registo por pergunta ----------
CREATE TABLE IF NOT EXISTS request_log (
  id                bigserial PRIMARY KEY,
  created_at        timestamptz NOT NULL DEFAULT now(),
  user_id           int REFERENCES users(id) ON DELETE SET NULL,
  username          text NOT NULL,
  role              text NOT NULL,
  conversation_id   int REFERENCES conversations(id) ON DELETE SET NULL,
  question          text NOT NULL,
  lang              text NOT NULL,
  intent            text,              -- etiqueta do classificador local (NULL = decidiu o LLM)
  confidence        real,
  kind              text NOT NULL,     -- sql, forecast, orders, no_sql, denied, error, exception
  sql_attempts      smallint NOT NULL DEFAULT 0,
  sql_failed        boolean NOT NULL DEFAULT false,   -- alguma tentativa de SQL falhou (mesmo que a 2.ª acerte)
  error             text,              -- erro técnico (só o admin vê)
  duration_ms       int NOT NULL,
  llm_calls         smallint NOT NULL DEFAULT 0,
  prompt_tokens     int NOT NULL DEFAULT 0,
  completion_tokens int NOT NULL DEFAULT 0,
  rating            smallint CHECK (rating IN (-1, 1)),   -- 👎 / 👍 do utilizador
  rated_at          timestamptz
);
CREATE INDEX IF NOT EXISTS idx_request_log_time ON request_log (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_request_log_rating ON request_log (created_at DESC) WHERE rating IS NOT NULL;

-- Cada resposta guardada aponta para o seu registo (para o 👍/👎 ao reabrir a conversa)
ALTER TABLE messages ADD COLUMN IF NOT EXISTS request_id bigint REFERENCES request_log(id) ON DELETE SET NULL;

-- Nada disto é visível ao role do LLM
REVOKE ALL ON request_log FROM assistente;
REVOKE ALL ON SEQUENCE request_log_id_seq FROM assistente;

-- ---------- Definições ----------
-- De cada conta (NULL = segue a predefinição da aplicação ou do browser)
CREATE TABLE IF NOT EXISTS user_settings (
  user_id    int PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  lang       text CHECK (lang IN ('pt', 'en', 'es', 'fr')),
  theme      text CHECK (theme IN ('light', 'dark', 'system')),
  accent     text CHECK (accent IN ('green', 'orange', 'blue', 'wine', 'purple', 'graphite')),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- Da aplicação (só o admin muda); só estas chaves existem
CREATE TABLE IF NOT EXISTS app_settings (
  key        text PRIMARY KEY CHECK (key IN ('default_accent', 'default_lang', 'show_demo_accounts', 'session_hours')),
  value      jsonb NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by int REFERENCES users(id) ON DELETE SET NULL
);

REVOKE ALL ON user_settings, app_settings FROM assistente;

-- Cor personalizada (#rrggbb) além das 6 predefinidas
ALTER TABLE user_settings DROP CONSTRAINT IF EXISTS user_settings_accent_check;
ALTER TABLE user_settings ADD CONSTRAINT user_settings_accent_check CHECK (
  accent IN ('green', 'orange', 'blue', 'wine', 'purple', 'graphite') OR accent ~ '^#[0-9a-f]{6}$');
