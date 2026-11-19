#!/bin/sh
# Arranque do contentor: prepara a base de dados e os modelos (só o que faltar)
# e depois inicia a API.
set -eu

# O .env aponta para localhost:5433 (uso fora do Docker).
# Dentro da rede do docker compose a base de dados é "db:5432".
to_docker_host() { echo "$1" | sed -E 's#@[^/@]+/#@db:5432/#'; }
export DATABASE_URL="$(to_docker_host "$DATABASE_URL")"
export READONLY_DATABASE_URL="$(to_docker_host "$READONLY_DATABASE_URL")"

# Só avisos e erros (os ficheiros são reaplicados em cada arranque: sem ruído de "already exists")
export PGOPTIONS="-c client_min_messages=warning"
psql_run() { psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q "$@"; }
step() { echo ""; echo "==> $*"; }

until pg_isready -d "$DATABASE_URL" -q; do
  echo "À espera da base de dados..."; sleep 2
done

# Passos já concluídos ficam registados: se um arranque cair a meio,
# o seguinte retoma (e refaz o que ficou incompleto) em vez de o saltar.
psql_run -c "CREATE TABLE IF NOT EXISTS setup_steps (step text PRIMARY KEY, done_at timestamptz NOT NULL DEFAULT now())"
is_done() { [ "$(psql_run -tAc "SELECT 1 FROM setup_steps WHERE step = '$1'")" = "1" ]; }
mark_done() { psql_run -c "INSERT INTO setup_steps (step) VALUES ('$1') ON CONFLICT DO NOTHING"; }
sql_true() { [ "$(psql_run -tAc "$1")" = "t" ]; }

# Instalações anteriores a setup_steps: reconhece o que já está feito pelos dados
# (a geração corre numa só transação: se há vendas, terminou bem)
if ! is_done data && sql_true "SELECT to_regclass('public.sales') IS NOT NULL AND EXISTS (SELECT 1 FROM sales)"; then
  mark_done data
  sql_true "SELECT to_regclass('public.sql_examples') IS NOT NULL AND EXISTS (SELECT 1 FROM sql_examples)" && mark_done rag
fi

# 1. Dados (só na 1.ª vez: demora alguns minutos)
if ! is_done data; then
  if sql_true "SELECT to_regclass('public.brands') IS NOT NULL"; then
    step "Arranque anterior incompleto: a limpar e a recomeçar"
    psql_run -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
    psql_run -c "CREATE TABLE setup_steps (step text PRIMARY KEY, done_at timestamptz NOT NULL DEFAULT now())"
  fi
  step "Primeira execução: criar tabelas e gerar dados fictícios"
  psql_run -f db/schema.sql
  python -m multistore_ai_assistant.data.generate
  python -m multistore_ai_assistant.data.generate_activity
  mark_done data
else
  # Acrescenta as vendas dos dias em falta até ontem (rápido; nada a fazer se já estiver em dia)
  step "Atualizar dados até ontem"
  python -m multistore_ai_assistant.data.generate_activity --extend
fi

# 2. Migrações (db/migrations): cada versão corre uma vez; as repetíveis (permissões,
#    vistas) quando mudam. Instalações antigas aplicam-nas todas sem perder nada.
step "Migrações da base de dados"
python -m multistore_ai_assistant.db.migrate
python -m multistore_ai_assistant.data.set_passwords
# Conta admin (só do dono): criada se ADMIN_USERNAME e ADMIN_PASSWORD estiverem no .env
if [ -n "${ADMIN_USERNAME:-}" ] && [ -n "${ADMIN_PASSWORD:-}" ]; then
  python -m multistore_ai_assistant.data.create_admin || echo "AVISO: a conta admin não foi criada (vê a mensagem acima)."
fi

if ! is_done rag; then
  step "Exemplos para o RAG"
  python -m multistore_ai_assistant.data.seed_examples
  mark_done rag
fi

# 3. Modelos (pasta models/ montada do teu computador: só treina o que faltar)
if [ ! -f models/sales_forecast.joblib ]; then
  step "Treinar o modelo de previsão de vendas"
  python -m multistore_ai_assistant.forecast.train
fi
if [ ! -f models/intent.joblib ] && [ ! -f models/intent-xlmr/model.safetensors ]; then
  step "Treinar o classificador de intenção (MiniLM)"
  python -m multistore_ai_assistant.intent.train
fi

step "Pronto! Abre http://localhost:${APP_PORT:-8001}"
exec uvicorn multistore_ai_assistant.api.main:app --host 0.0.0.0 --port 8001
