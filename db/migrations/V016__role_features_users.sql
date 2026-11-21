-- Funcionalidade «users» (gestão de contas) por perfil. Idempotente.
-- Todos os perfis ficam com ela, como até agora: quem gere contas continua a precisar
-- do módulo «users» na própria conta. A funcionalidade «admin» é só do perfil admin.

ALTER TABLE role_features DROP CONSTRAINT IF EXISTS role_features_feature_check;
ALTER TABLE role_features ADD CONSTRAINT role_features_feature_check
  CHECK (feature IN ('chat', 'forecast', 'orders', 'dashboard', 'review', 'users', 'admin'));

DELETE FROM role_features WHERE feature = 'admin' AND role <> 'admin';
ALTER TABLE role_features DROP CONSTRAINT IF EXISTS role_features_admin_only;
ALTER TABLE role_features ADD CONSTRAINT role_features_admin_only
  CHECK (feature <> 'admin' OR role = 'admin');

INSERT INTO role_features (role, feature) VALUES
  ('admin', 'users'),
  ('imperador', 'users'),
  ('marca', 'users'),
  ('loja', 'users')
ON CONFLICT DO NOTHING;
