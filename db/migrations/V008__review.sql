-- Revisão dos 👎: quem tem o módulo "teach" (admin / Imperador) corrige o SQL e ensina o RAG, ou ignora.
-- Um 👎 sai da lista "Para rever" quando tem reviewed_at.

ALTER TABLE request_log ADD COLUMN IF NOT EXISTS reviewed_at   timestamptz;
ALTER TABLE request_log ADD COLUMN IF NOT EXISTS reviewed_by   text;
ALTER TABLE request_log ADD COLUMN IF NOT EXISTS review_action text;

ALTER TABLE request_log DROP CONSTRAINT IF EXISTS request_log_review_check;
ALTER TABLE request_log ADD CONSTRAINT request_log_review_check CHECK (
  (reviewed_at IS NULL AND reviewed_by IS NULL AND review_action IS NULL)
  OR (reviewed_at IS NOT NULL AND reviewed_by IS NOT NULL AND review_action IN ('taught', 'dismissed')));

-- A lista só lê 👎 por rever: índice parcial pequeno
CREATE INDEX IF NOT EXISTS request_log_to_review ON request_log (created_at DESC)
  WHERE rating = -1 AND reviewed_at IS NULL;
