CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS sql_examples (
  id         serial PRIMARY KEY,
  question   text UNIQUE NOT NULL,
  sql        text NOT NULL,
  embedding  vector(384) NOT NULL,
  source     text NOT NULL DEFAULT 'seed',   -- 'seed' ou 'feedback' (👍 no chat)
  created_at timestamp NOT NULL DEFAULT now()
);

GRANT SELECT ON sql_examples TO assistente;