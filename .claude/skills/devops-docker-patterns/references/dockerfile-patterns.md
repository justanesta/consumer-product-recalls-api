# Dockerfile Patterns Reference

Detailed patterns for writing production-quality Dockerfiles, covering multi-stage builds, instruction usage, and common configurations for Python, Node.js, and general applications.

---

## Multi-Stage Builds

Multi-stage builds use multiple `FROM` statements. Each stage starts a new build context. You selectively copy artifacts from earlier stages into the final image, leaving build tools behind.

### Python Multi-Stage Build

```dockerfile
# Stage 1: Build wheels for all dependencies
FROM python:3.12-slim AS builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir=/wheels -r requirements.txt

# Stage 2: Runtime image with no compiler
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels
COPY . .
USER nobody
CMD ["gunicorn", "app:create_app()", "--bind", "0.0.0.0:8000", "--workers", "4"]
```

### Node.js Multi-Stage Build

```dockerfile
# Stage 1: Install dependencies and build
FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build && npm prune --production

# Stage 2: Minimal runtime
FROM node:20-alpine
WORKDIR /app
RUN addgroup -S appgroup && adduser -S appuser -G appgroup
COPY --from=builder --chown=appuser:appgroup /app/dist ./dist
COPY --from=builder --chown=appuser:appgroup /app/node_modules ./node_modules
COPY --from=builder --chown=appuser:appgroup /app/package.json ./
USER appuser
EXPOSE 3000
CMD ["node", "dist/server.js"]
```

### Go Static Binary

```dockerfile
FROM golang:1.22-alpine AS builder
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /app ./cmd/server

FROM scratch
COPY --from=builder /app /app
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/
EXPOSE 8080
ENTRYPOINT ["/app"]
```

---

## ARG and ENV

`ARG` is available only during build. `ENV` persists into the running container. Use `ARG` for build-time configuration and `ENV` for runtime configuration.

```dockerfile
# Build-time argument with default
ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim

# Build-time only -- not visible at runtime
ARG BUILD_DATE
ARG GIT_SHA
LABEL org.opencontainers.image.created="${BUILD_DATE}"
LABEL org.opencontainers.image.revision="${GIT_SHA}"

# Runtime environment variable
ENV APP_ENV=production
ENV LOG_LEVEL=info
ENV PORT=8000

WORKDIR /app
COPY . .
EXPOSE ${PORT}
CMD ["python", "server.py"]
```

Build with custom args:

```bash
docker build \
  --build-arg PYTHON_VERSION=3.11 \
  --build-arg BUILD_DATE=$(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --build-arg GIT_SHA=$(git rev-parse --short HEAD) \
  -t myapp:latest .
```

### ARG/ENV Edge Cases

- An `ARG` declared before the first `FROM` is only available in `FROM` lines.
- An `ARG` declared after `FROM` is scoped to that build stage only.
- To use a pre-`FROM` ARG later, redeclare it inside the stage without a default.
- `ENV` overrides `ARG` if both use the same name.

```dockerfile
ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}

# Must redeclare to use inside the stage
ARG BASE_IMAGE
RUN echo "Built from ${BASE_IMAGE}"
```

---

## COPY vs ADD

Always prefer `COPY` for copying local files. `ADD` has two implicit behaviors that cause unexpected results.

| Instruction | Behavior |
|---|---|
| `COPY src dest` | Copies files from build context to image. Predictable. |
| `ADD src dest` | Copies files, but also auto-extracts `.tar.gz` archives and supports URL fetching. |

```dockerfile
# Correct: use COPY for local files
COPY requirements.txt .
COPY src/ ./src/

# Acceptable: use ADD only when you want automatic extraction
ADD app.tar.gz /app/

# Wrong: using ADD for a URL -- use curl in a RUN instead
# ADD https://example.com/file.txt /app/   <-- avoid this
RUN curl -fsSL https://example.com/file.txt -o /app/file.txt
```

### COPY --chown and --chmod

```dockerfile
# Set ownership during copy to avoid extra RUN chown layer
COPY --chown=appuser:appgroup src/ /app/src/

# Set permissions during copy (BuildKit required)
COPY --chmod=755 scripts/entrypoint.sh /entrypoint.sh
```

---

## ENTRYPOINT vs CMD

`ENTRYPOINT` defines the executable. `CMD` provides default arguments. Together they form the full command.

### Exec Form vs Shell Form

```dockerfile
# Exec form (preferred) -- PID 1 receives signals directly
ENTRYPOINT ["python", "server.py"]
CMD ["--port", "8000"]
# Resulting command: python server.py --port 8000

# Shell form -- runs under /bin/sh -c, does NOT receive SIGTERM
ENTRYPOINT python server.py
# Resulting command: /bin/sh -c "python server.py"
```

Always use exec form so the process runs as PID 1 and receives signals (SIGTERM for graceful shutdown).

### Entrypoint Script Pattern

Use a shell script as ENTRYPOINT when you need initialization logic before the main process.

```dockerfile
COPY scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "app:create_app()", "--bind", "0.0.0.0:8000"]
```

```bash
#!/bin/sh
set -e

# Run database migrations
python manage.py migrate --noinput

# Execute the CMD
exec "$@"
```

The `exec "$@"` replaces the shell with the CMD process so it becomes PID 1.

---

## .dockerignore

A `.dockerignore` file excludes files from the build context, reducing build time and preventing secrets or unnecessary files from entering the image.

```
# Version control
.git
.gitignore

# Dependencies (will be installed inside the image)
node_modules
__pycache__
*.pyc
.venv
venv

# IDE and editor files
.vscode
.idea
*.swp
*.swo

# Docker files (not needed inside the image)
Dockerfile*
docker-compose*.yml
.dockerignore

# Documentation and tests
*.md
tests/
docs/

# Environment and secrets
.env
.env.*
*.pem
*.key

# OS files
.DS_Store
Thumbs.db
```

### Edge Cases

- Patterns work like `.gitignore` but with one key difference: `!` exceptions must come after the exclusion they override.
- Each build stage gets the full context minus ignored files. You cannot ignore files for only one stage.
- If your `.dockerignore` is missing, the entire build context (potentially gigabytes) gets sent to the daemon.

```
# Exclude everything, then whitelist
*
!src/
!package.json
!package-lock.json
!tsconfig.json
```

---

## Layer Ordering Strategy

Order instructions from least-frequently-changed to most-frequently-changed:

```dockerfile
FROM python:3.12-slim           # 1. Base image (rarely changes)
WORKDIR /app                    # 2. Working directory (never changes)
RUN apt-get update && \         # 3. System packages (occasionally changes)
    apt-get install -y libpq5
COPY requirements.txt .         # 4. Dependency manifest (changes sometimes)
RUN pip install -r requirements.txt  # 5. Dependency install (changes sometimes)
COPY . .                        # 6. Application source (changes frequently)
CMD ["python", "server.py"]     # 7. Startup command (rarely changes)
```

If you change only application source code, layers 1-5 are cached and Docker only rebuilds from step 6 onward.
