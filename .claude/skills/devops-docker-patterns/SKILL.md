---
name: devops-docker-patterns
description: Docker containerization patterns including Dockerfile best practices, Compose orchestration, image optimization, networking, volumes, and security hardening for production workloads.
---

# Docker Patterns

## Core Principles

1. **Minimal images** -- Use the smallest base image that satisfies your runtime requirements. Every unnecessary package increases attack surface and image size.
2. **Immutable infrastructure** -- Containers should be disposable and reproducible. Never patch a running container; rebuild and redeploy.
3. **Layer caching** -- Order Dockerfile instructions from least-frequently-changed to most-frequently-changed so Docker can reuse cached layers.
4. **Security by default** -- Run processes as non-root, scan images for vulnerabilities, and never bake secrets into images.
5. **One process per container** -- Each container should run a single concern. Use Compose or orchestrators to combine services.

---

## Dockerfile Best Practices

Use multi-stage builds to separate build dependencies from the final runtime image. This keeps production images small and free of compilers, package managers, and source code.

```dockerfile
# ---- Build stage ----
FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- Runtime stage ----
FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /install /usr/local
COPY . .
USER nobody
EXPOSE 8000
CMD ["gunicorn", "app:create_app()", "--bind", "0.0.0.0:8000"]
```

Order layers so that dependency installation comes before source code COPY. This way, code changes do not invalidate the expensive dependency-install layer.

See [dockerfile-patterns](references/dockerfile-patterns.md) for: multi-stage builds, ARG/ENV usage, COPY vs ADD, ENTRYPOINT vs CMD patterns, and .dockerignore configuration.

---

## Docker Compose Patterns

Define services, networks, and volumes declaratively. Use `depends_on` with health checks to control startup order reliably.

```yaml
services:
  api:
    build: .
    ports:
      - "8000:8000"
    depends_on:
      db:
        condition: service_healthy
    environment:
      DATABASE_URL: postgres://app:secret@db:5432/mydb
    networks:
      - backend

  db:
    image: postgres:16-alpine
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app"]
      interval: 5s
      timeout: 3s
      retries: 5
    networks:
      - backend

volumes:
  pgdata:

networks:
  backend:
```

See [compose-patterns](references/compose-patterns.md) for: service definitions, healthcheck strategies, profiles, override files, and environment management.

---

## Image Optimization

Choose the right base image for your workload. Alpine images are small but use musl libc, which can cause compatibility issues with some native extensions. Distroless images contain only the application runtime.

```dockerfile
# Node.js production image -- 5x smaller than node:20
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --production
COPY . .
RUN npm run build

FROM gcr.io/distroless/nodejs20-debian12
WORKDIR /app
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/node_modules ./node_modules
CMD ["dist/server.js"]
```

See [image-optimization](references/image-optimization.md) for: base image selection guide, layer caching strategies, .dockerignore examples, and distroless versus Alpine trade-offs.

---

## Volume and Networking Patterns

Use named volumes for persistent data and bind mounts only for development. Choose the right network driver for your deployment model.

```yaml
services:
  app:
    image: myapp:latest
    volumes:
      - app-data:/app/data          # Named volume for persistence
      - ./config:/app/config:ro     # Bind mount, read-only
      - tmp:/tmp                    # tmpfs for ephemeral scratch
    networks:
      - frontend
      - backend

volumes:
  app-data:
    driver: local
  tmp:
    driver_opts:
      type: tmpfs
      device: tmpfs
```

See [networking-volumes](references/networking-volumes.md) for: bridge/host/overlay network drivers, named volume lifecycle, bind mount patterns, and tmpfs usage.

---

## Security Hardening

Always run containers as a non-root user. Use Docker secrets or environment variables from a vault -- never embed credentials in the image.

```dockerfile
FROM python:3.12-slim
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser
WORKDIR /app
COPY --chown=appuser:appuser . .
RUN pip install --no-cache-dir -r requirements.txt

USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
CMD ["gunicorn", "app:create_app()", "--bind", "0.0.0.0:8000"]
```

See [security-patterns](references/security-patterns.md) for: non-root user setup, secrets management, image scanning with Trivy/Grype, read-only filesystem configuration, and capability dropping.

---

## Health Checks and Logging

Define health checks so orchestrators can detect and replace unhealthy containers. Log to stdout/stderr so the Docker logging driver can collect output.

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["curl", "-f", "http://localhost:8000/health"] || exit 1
```

```yaml
services:
  app:
    image: myapp:latest
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
```

Write application logs to stdout, not to files inside the container. This lets Docker, Kubernetes, and log aggregators handle rotation and shipping.

---

## Anti-Patterns

| Avoid | Use Instead |
|---|---|
| `FROM ubuntu:latest` as base image | `FROM python:3.12-slim` or distroless images sized for your runtime |
| Running as root inside containers | Create a dedicated user with `useradd` and switch with `USER` |
| `COPY . .` before installing dependencies | Copy dependency manifests first, install, then copy source |
| Hardcoding secrets in Dockerfile `ENV` | Docker secrets, mounted env files, or vault integration |
| Using `ADD` for local files | Use `COPY` -- `ADD` has implicit tar extraction and URL fetch side effects |
| `apt-get install` without cleanup | Chain `apt-get update && apt-get install -y ... && rm -rf /var/lib/apt/lists/*` |
| One giant Dockerfile stage | Multi-stage builds to separate build tools from runtime |
| No `.dockerignore` file | Maintain `.dockerignore` to exclude `.git`, `node_modules`, `__pycache__` |
| `docker-compose up` with no health checks | Use `depends_on` with `condition: service_healthy` |
| Storing data in container writable layer | Named volumes for persistence, tmpfs for ephemeral data |

---

## Performance

- **Layer caching** -- Place `COPY requirements.txt` and `RUN pip install` before `COPY . .` to avoid reinstalling dependencies on every code change.
- **BuildKit** -- Enable with `DOCKER_BUILDKIT=1`. Provides parallel stage execution, better caching, and secret mounts (`--mount=type=secret`).
- **Multi-stage size reduction** -- A Python multi-stage build typically reduces image size from 900 MB to under 150 MB.
- **Compose startup** -- Use `depends_on` with health conditions instead of arbitrary `sleep` commands for reliable service ordering.
- **Resource limits** -- Set `deploy.resources.limits` in Compose to prevent a single container from consuming all host memory or CPU.
- **Image layer squashing** -- Use `docker build --squash` or combine related `RUN` commands to reduce final layer count without sacrificing cache efficiency during development.

source: Docker Official Documentation, Dockerfile Best Practices, Docker Compose Specification
