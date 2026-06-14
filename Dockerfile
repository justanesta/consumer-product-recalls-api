# syntax=docker/dockerfile:1
# ---- builder: resolve + install the locked deps into a venv with uv ----
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
# Install deps first (cached unless pyproject/uv.lock change), then the project itself.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev

# ---- runtime: slim, non-root, no build tools ----
FROM python:3.12-slim
RUN groupadd -r app && useradd -r -g app -u 10001 app
WORKDIR /app
COPY --from=builder --chown=app:app /app /app
ENV PATH="/app/.venv/bin:$PATH" \
    PORT=8080 \
    ENVIRONMENT=production
USER app
EXPOSE 8080
# NEON_DATABASE_URL_RO is provided at runtime (Fly secret); never baked into the image.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import sys,urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health').status==200 else 1)"
CMD ["sh", "-c", "uvicorn --factory recalls_api.main:create_app --host 0.0.0.0 --port ${PORT} --proxy-headers"]
