-- A conta pública de demonstração do Imperador ("pedro", password no README) fica sem o módulo "teach".
-- Esse módulo grava exemplos no RAG que servem todas as contas e aprova os 👎 em /review:
-- com a password pública, qualquer visitante o podia usar. Ensinar fica para a conta admin (privada).
--
-- Só mexe se a conta ainda usa os módulos por defeito (modules NULL): uma escolha feita
-- depois pelo admin, na página Contas, não é desfeita.
UPDATE users
SET modules = ARRAY['sql', 'forecast', 'orders', 'users']
WHERE username = 'pedro' AND modules IS NULL;
