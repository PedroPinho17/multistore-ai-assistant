-- Gestão dos exemplos do RAG (página "Ensinar" → Exemplos, módulo "teach").
-- source: seed (instalação), feedback (botão "guardar como exemplo"), review (👎 corrigido), manual (criado na página)

ALTER TABLE sql_examples ADD COLUMN IF NOT EXISTS created_by   text;
ALTER TABLE sql_examples ADD COLUMN IF NOT EXISTS updated_at   timestamptz;
ALTER TABLE sql_examples ADD COLUMN IF NOT EXISTS updated_by   text;
-- Quantas vezes entrou no prompt do gerador de SQL (mostra que exemplos servem e quais nunca são usados)
ALTER TABLE sql_examples ADD COLUMN IF NOT EXISTS uses         int NOT NULL DEFAULT 0;
ALTER TABLE sql_examples ADD COLUMN IF NOT EXISTS last_used_at timestamptz;

ALTER TABLE sql_examples DROP CONSTRAINT IF EXISTS sql_examples_source_check;
ALTER TABLE sql_examples ADD CONSTRAINT sql_examples_source_check
  CHECK (source IN ('seed', 'feedback', 'review', 'manual'));

COMMENT ON COLUMN sql_examples.source IS 'seed, feedback (guardar como exemplo), review (👎 corrigido), manual (página Exemplos)';
