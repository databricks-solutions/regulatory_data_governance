# App RC18 (FastAPI + SPA) em container, alternativa ao Databricks Apps. Contexto de build = app/:
#   docker build -f docker/Dockerfile -t rc18-app app

# ── SPA: build a partir do código-fonte (não do frontend_dist versionado) ──
FROM node:22-slim AS frontend
# Mirror npm interno, se a rede não alcança o registry público.
ARG NPM_CONFIG_REGISTRY
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
# Lista explícita: COPY do diretório traria o node_modules do host em builders sem .dockerignore.
COPY frontend/svelte.config.js frontend/vite.config.js ./
COPY frontend/src ./src
COPY frontend/static ./static
RUN npm run build

# ── Runtime: mesmo Python do Databricks Apps ──
FROM python:3.11-slim
# Mirror PyPI interno, idem.
ARG PIP_INDEX_URL
# Sem env de workspace o app sobe em mock. Workers via WEB_CONCURRENCY (2, como o app.yaml).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    USE_MOCK_BACKEND=true \
    WEB_CONCURRENCY=2
# 3 níveis de profundidade de propósito: main.py lê `parents[2]/.env` e quebra com o código em /app.
WORKDIR /opt/rc18/app/backend

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Lista explícita: ficam fora tests/, .databricks/, static/brand/ e o frontend_dist versionado.
# Pacote novo no backend precisa entrar aqui.
COPY backend/*.py backend/brand_config.json ./
COPY backend/routers ./routers
COPY --from=frontend /src/build ./frontend_dist

# Sem root; grupo 0 para rodar com UID arbitrário (OpenShift). Só o branding é gravável.
RUN useradd --uid 10001 --gid 0 --no-create-home rc18 \
 && mkdir -p static/brand \
 && chown -R 10001:0 brand_config.json static \
 && chmod -R g=u brand_config.json static
USER 10001

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/openapi.json', timeout=4)"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
