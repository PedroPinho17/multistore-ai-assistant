-- Conversas guardadas por utilizador (o assistente NÃO pode ler estas tabelas)
CREATE TABLE IF NOT EXISTS conversations (
  id          serial PRIMARY KEY,
  user_id     int NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title       text NOT NULL DEFAULT 'Nova conversa',
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS messages (
  id               serial PRIMARY KEY,
  conversation_id  int NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role             text NOT NULL CHECK (role IN ('user', 'assistant')),
  content          text NOT NULL,
  sql              text,          -- a query usada (para o "› Fonte")
  kind             text,          -- 'sql', 'forecast', 'orders', 'no_sql'
  created_at       timestamptz NOT NULL DEFAULT now()
);

-- Barra lateral: conversas do utilizador, mais recentes primeiro
CREATE INDEX IF NOT EXISTS idx_conversations_user
  ON conversations (user_id, updated_at DESC);
-- Abrir uma conversa: mensagens por ordem
CREATE INDEX IF NOT EXISTS idx_messages_conversation
  ON messages (conversation_id, id);

-- O R__readonly.sql dá SELECT automático em tabelas novas ao assistente; aqui tiramos isso
REVOKE ALL ON conversations, messages FROM assistente;

-- Migração: versões antigas gravavam as respostas com erro sem kind e com o SQL
-- partido, que depois voltava ao LLM como memória e aparecia com 👍 na Fonte.
UPDATE messages SET kind = 'error', sql = NULL
WHERE role = 'assistant' AND kind IS NULL
  AND (content LIKE 'Não consegui responder%' OR content LIKE 'I couldn''t answer%'
       OR content LIKE 'No he podido responder%' OR content LIKE 'Je n''ai pas pu répondre%');