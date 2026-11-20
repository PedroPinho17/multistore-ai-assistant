# ---- Stage 1: Vue SPA (Vite) ----
FROM node:22-bookworm-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: API + chat ----
# Imagem da aplicação (API + chat). A base de dados é o serviço "db" do docker-compose.
FROM python:3.13-slim

# psql: para aplicar os ficheiros db/*.sql no primeiro arranque
RUN apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.13.8 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/opt/hf

WORKDIR /app

# 1.º só as dependências (camada em cache enquanto o uv.lock não mudar).
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Modelo de embeddings: antes de copiar src/ e o dist, para mudanças de código não o refazerem
RUN HF_HUB_OFFLINE=0 python -c "from sentence_transformers import SentenceTransformer; \
SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')"
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1

# 2.º o pacote Python (antes de data/dist: mudanças nesses não reinstalamos o projeto)
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

COPY db ./db
COPY data ./data
COPY --from=frontend /frontend/dist ./frontend/dist

COPY docker/entrypoint.sh /entrypoint.sh

# Utilizador sem privilégios; models/ e eval/ são escritos no 1.º arranque, data/avatars/ pelas fotos de perfil
RUN useradd --create-home --uid 1000 app \
 && mkdir -p /app/models /app/eval /app/data/avatars \
 && chown -R app:app /app/models /app/eval /app/data/avatars \
 && sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh
USER app

EXPOSE 8001
HEALTHCHECK --interval=15s --timeout=5s --start-period=30m --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health', timeout=4)"

ENTRYPOINT ["/entrypoint.sh"]
