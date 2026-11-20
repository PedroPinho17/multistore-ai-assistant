-- Foto de perfil em ficheiro: um WebP 256×256 por conta, guardado na pasta de avatares
-- (AVATAR_DIR, por defeito data/avatars, montada como volume no docker-compose).
-- Aqui fica só o nome do ficheiro (UUID aleatório) e quando mudou (para o ?v= da URL).
--
-- A coluna antiga "avatar" (data URL, V005) deixa de ser lida pela aplicação; fica
-- intacta para não apagar fotos já guardadas e pode ser removida numa migração futura.

ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_path text;
ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_updated_at timestamptz;

-- Só um nome gerado pela app: nunca um caminho (sem "/" nem "..")
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_avatar_path_check;
ALTER TABLE users ADD CONSTRAINT users_avatar_path_check
  CHECK (avatar_path IS NULL OR avatar_path ~ '^[0-9a-f]{32}\.webp$');
