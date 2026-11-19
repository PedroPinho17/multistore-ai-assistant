-- Cache semântica: perguntas já respondidas com SQL, para reaproveitar o SQL de uma
-- pergunta muito parecida sem chamar o LLM. O SQL corre sempre de novo com o RLS de
-- quem pergunta; só vale no próprio dia (perguntas como "ontem" mudam de data).
CREATE TABLE IF NOT EXISTS query_cache (
  id          bigserial PRIMARY KEY,
  scope       text NOT NULL,                 -- perfil de dados: imperador, marca ou loja
  question    text NOT NULL,
  embedding   vector(384) NOT NULL,          -- MiniLM multilingue (o mesmo do RAG)
  sql         text NOT NULL,
  hits        int NOT NULL DEFAULT 0,
  created_at  timestamptz NOT NULL DEFAULT now(),
  last_hit_at timestamptz
);
CREATE INDEX IF NOT EXISTS idx_query_cache_scope_day ON query_cache (scope, created_at DESC);

-- Registo: a resposta veio da cache?
ALTER TABLE request_log ADD COLUMN IF NOT EXISTS cache_hit boolean NOT NULL DEFAULT false;

REVOKE ALL ON query_cache FROM assistente;
