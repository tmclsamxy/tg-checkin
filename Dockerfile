# ---------------------------------------------------------------------------
# stage 1 — build the Vue frontend
# ---------------------------------------------------------------------------
FROM node:22-alpine AS frontend

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
# `npm ci` guarantees the image matches the lockfile exactly.
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
# override outDir so the assets land inside the build context
RUN npx vite build --outDir dist

# ---------------------------------------------------------------------------
# stage 2 — python runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/app/data \
    TZ=Asia/Shanghai

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/

# built assets are served by FastAPI from backend/app/static
COPY --from=frontend /build/dist ./backend/app/static

RUN useradd --uid 10001 --create-home appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
VOLUME ["/app/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT:-8000}/api/health" || exit 1

# shell form 才能展开 ${PORT}，用于 host 网络模式下改监听端口
CMD python -m uvicorn backend.app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
