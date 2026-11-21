-- Funcionalidades por perfil (chat, previsão, encomendas, painel, revisão, admin).
-- Idempotente. O admin edita as linhas; a semente só entra se o par ainda não existir,
-- para uma reaplicação não desfazer o que o admin mudou.
-- Por defeito cada perfil fica com o que já podia fazer: o admin tem tudo;
-- o imperador tem chat, previsão, encomendas, painel e revisão (rentabilidade);
-- marca e loja têm chat, previsão, encomendas e painel.

CREATE TABLE IF NOT EXISTS role_features (
  role    text NOT NULL,
  feature text NOT NULL,
  PRIMARY KEY (role, feature),
  CONSTRAINT role_features_role_check
    CHECK (role IN ('admin', 'imperador', 'marca', 'loja')),
  CONSTRAINT role_features_feature_check
    CHECK (feature IN ('chat', 'forecast', 'orders', 'dashboard', 'review', 'admin'))
);

INSERT INTO role_features (role, feature) VALUES
  ('admin', 'chat'),
  ('admin', 'forecast'),
  ('admin', 'orders'),
  ('admin', 'dashboard'),
  ('admin', 'review'),
  ('admin', 'admin'),
  ('imperador', 'chat'),
  ('imperador', 'forecast'),
  ('imperador', 'orders'),
  ('imperador', 'dashboard'),
  ('imperador', 'review'),
  ('marca', 'chat'),
  ('marca', 'forecast'),
  ('marca', 'orders'),
  ('marca', 'dashboard'),
  ('loja', 'chat'),
  ('loja', 'forecast'),
  ('loja', 'orders'),
  ('loja', 'dashboard')
ON CONFLICT DO NOTHING;

REVOKE ALL ON role_features FROM assistente;
