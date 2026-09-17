FROM node:22-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.11.17 AS uv
FROM python:3.12-slim-bookworm AS backend
COPY --from=uv /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/
RUN uv sync --frozen --no-dev

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    MDT_DB_PATH=/data/mdt.db
WORKDIR /app
RUN groupadd --gid 10001 mdt \
    && useradd --uid 10001 --gid 10001 --no-create-home --home-dir /app mdt \
    && mkdir /data \
    && chown 10001:10001 /data
COPY --from=backend /app/.venv /app/.venv
COPY --from=backend /app/src /app/src
COPY --from=frontend /build/frontend/dist /app/frontend/dist
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)"
CMD ["python", "-m", "uvicorn", "mdt.app:app", "--host", "0.0.0.0", "--port", "8000"]
