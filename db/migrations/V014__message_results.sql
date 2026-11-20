-- Dados de cada resposta guardados com a mensagem: {"columns": [...], "rows": [[...], ...], "truncated": bool}
-- (no máximo 200 linhas). O PDF da conversa usa só isto: nunca volta a correr SQL, previsões
-- ou encomendas, por isso mostra exatamente o que o utilizador viu e não ignora os módulos.
-- Mensagens antigas ficam a NULL ("tabela não disponível" no PDF).

ALTER TABLE messages ADD COLUMN IF NOT EXISTS result jsonb;

ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_result_check;
ALTER TABLE messages ADD CONSTRAINT messages_result_check CHECK (
  result IS NULL OR (
    jsonb_typeof(result -> 'columns') = 'array'
    AND jsonb_typeof(result -> 'rows') = 'array'
    AND jsonb_array_length(result -> 'rows') <= 200
    AND jsonb_typeof(result -> 'truncated') = 'boolean'));
