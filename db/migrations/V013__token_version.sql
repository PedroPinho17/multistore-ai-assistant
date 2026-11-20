-- Revogar sessões quando a password muda: cada JWT leva a versão da conta ("tv").
-- Mudar ou repor a password soma 1 a token_version e os tokens com a versão antiga
-- deixam de valer. Um contador, não uma data: não depende dos relógios da app e da
-- BD nem da precisão do "iat" (segundos inteiros).

ALTER TABLE users ADD COLUMN IF NOT EXISTS token_version int NOT NULL DEFAULT 0;

-- Versão anterior desta migração (nunca publicada) usava uma data
ALTER TABLE users DROP COLUMN IF EXISTS password_changed_at;
