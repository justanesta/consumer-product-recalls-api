# Image Optimization Reference

Detailed strategies for reducing Docker image size, improving build speed through layer caching, selecting appropriate base images, and configuring `.dockerignore` for efficient builds.

---

## Base Image Selection

Choosing the right base image has the largest impact on final image size and security posture.

### Image Size Comparison

| Base Image | Approximate Size | Use Case |
|---|---|---|
| `ubuntu:24.04` | 78 MB | When you need apt and a full userland |
| `python:3.12` | 920 MB | Development only -- includes compiler toolchain |
| `python:3.12-slim` | 130 MB | Production Python -- minimal Debian packages |
| `python:3.12-alpine` | 52 MB | Smallest Python, but musl libc may break some packages |
| `node:20` | 1.1 GB | Development only |
| `node:20-alpine` | 135 MB | Production Node.js |
| `gcr.io/distroless/python3` | 52 MB | No shell, no package manager -- hardened runtime |
| `gcr.io/distroless/nodejs20-debian12` | 130 MB | Distroless Node.js |
| `scratch` | 0 MB | Static binaries only (Go, Rust) |

### Decision Guide

```
Do you need a shell for debugging?
  Yes --> Use -slim or -alpine variant
  No  --> Use distroless or scratch

Does your app use native C extensions?
  Yes --> Use -slim (glibc) -- Alpine's musl libc causes issues with numpy, pandas, psycopg2
  No  --> Alpine is fine

Is this a statically compiled binary?
  Yes --> Use scratch (smallest possible, zero attack surface)
  No  --> Use the appropriate runtime image
```

### Python: slim vs Alpine

```dockerfile
# PREFERRED for Python with native extensions
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
```

```dockerfile
# Alpine: smaller but needs extra build deps for native packages
FROM python:3.12-alpine
RUN apk add --no-cache postgresql-libs && \
    apk add --no-cache --virtual .build-deps gcc musl-dev postgresql-dev && \
    pip install --no-cache-dir -r requirements.txt && \
    apk del .build-deps
```

The Alpine variant requires installing build dependencies, compiling, then removing them. This is slower and error-prone compared to using `-slim` with pre-built wheels.

---

## Layer Caching Strategies

Docker caches each layer. When a layer changes, all subsequent layers are rebuilt. Structure your Dockerfile to maximize cache hits.

### Dependency-First Pattern

```dockerfile
FROM node:20-alpine
WORKDIR /app

# Layer 1: package files change less often than source code
COPY package.json package-lock.json ./

# Layer 2: expensive npm install is cached until package files change
RUN npm ci --production

# Layer 3: source changes invalidate only this layer and below
COPY . .

RUN npm run build
```

### Selective COPY for Better Caching

```dockerfile
FROM python:3.12-slim
WORKDIR /app

# Copy ONLY the dependency file first
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy configuration files (change less often than source)
COPY alembic.ini .
COPY alembic/ ./alembic/

# Copy source code last (changes most often)
COPY src/ ./src/
```

### BuildKit Cache Mounts

BuildKit cache mounts persist package manager caches across builds, dramatically speeding up dependency installation.

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .

# Cache pip downloads between builds
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY . .
```

```dockerfile
# syntax=docker/dockerfile:1
FROM node:20-alpine
WORKDIR /app
COPY package.json package-lock.json ./

# Cache npm modules between builds
RUN --mount=type=cache,target=/root/.npm \
    npm ci --production

COPY . .
```

```bash
# Enable BuildKit
export DOCKER_BUILDKIT=1
docker build -t myapp .
```

---

## .dockerignore Patterns

A well-configured `.dockerignore` reduces build context size, speeds up builds, and prevents sensitive files from entering the image.

### Python Project

```
# Version control
.git
.gitignore

# Virtual environments
.venv
venv
env

# Byte-compiled files
__pycache__
*.pyc
*.pyo
*.egg-info
dist
build

# IDE
.vscode
.idea
*.swp

# Testing and CI
.pytest_cache
.coverage
htmlcov
.tox
.mypy_cache

# Docker files
Dockerfile*
docker-compose*.yml
.dockerignore

# Documentation
*.md
docs/
LICENSE

# Environment and secrets
.env
.env.*
*.pem
*.key
```

### Whitelist Approach

When your project contains many files you do not need, ignore everything and whitelist specific paths.

```
*
!src/
!package.json
!package-lock.json
!tsconfig.json
```

---

## Distroless Images

Distroless images contain only the language runtime and your application. No shell, no package manager, no OS utilities. This minimizes attack surface.

### Python Distroless

```dockerfile
FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt
COPY . .

FROM gcr.io/distroless/python3-debian12
WORKDIR /app
COPY --from=builder /install /usr/local
COPY --from=builder /app .
CMD ["server.py"]
```

### Node.js Distroless

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --production
COPY . .
RUN npm run build

FROM gcr.io/distroless/nodejs20-debian12
WORKDIR /app
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
CMD ["dist/server.js"]
```

### Debugging Distroless

Distroless images have no shell. To debug, use the `:debug` tag which includes BusyBox.

```bash
# Use debug variant for troubleshooting
docker run --rm -it gcr.io/distroless/python3-debian12:debug sh

# In production, exec into a sidecar or ephemeral debug container
docker run --rm -it --pid=container:myapp --network=container:myapp busybox sh
```

---

## Reducing Layer Count

Each `RUN`, `COPY`, and `ADD` creates a new layer. Combine related operations to reduce layers without sacrificing cache efficiency.

```dockerfile
# Bad: 3 separate layers for package installation
RUN apt-get update
RUN apt-get install -y curl
RUN rm -rf /var/lib/apt/lists/*

# Good: single layer with cleanup
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      curl \
      ca-certificates \
    && rm -rf /var/lib/apt/lists/*
```

### When NOT to Combine

Do not combine dependency installation with source code copying. Keep them separate so that changing source code does not invalidate the dependency cache.

```dockerfile
# Keep separate for caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# This layer rebuilds on code changes but pip install above stays cached
COPY . .
```

---

## Build Context Size

Monitor build context size with `docker build --no-cache -t test . 2>&1 | grep "Sending build context"`. A project with `node_modules` (500 MB) and `.git` (200 MB) wastes 700 MB per build. A proper `.dockerignore` eliminates this entirely.
