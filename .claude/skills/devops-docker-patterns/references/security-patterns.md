# Security Patterns Reference

Detailed patterns for securing Docker containers, covering non-root users, secrets management, image scanning, read-only filesystems, capability dropping, and runtime security configuration.

---

## Non-Root Users

By default, Docker containers run as root. If an attacker escapes the application, they have root access inside the container (and potentially on the host if there are kernel vulnerabilities). Always create and switch to a dedicated user.

### Debian/Ubuntu-Based Images

```dockerfile
FROM python:3.12-slim

# Create a system group and user with no login shell and no home directory
RUN groupadd -r appuser && \
    useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

# Install dependencies as root
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files with correct ownership
COPY --chown=appuser:appuser . .

# Switch to non-root user for all subsequent commands
USER appuser

EXPOSE 8000
CMD ["gunicorn", "app:create_app()", "--bind", "0.0.0.0:8000"]
```

### Alpine-Based Images

```dockerfile
FROM node:20-alpine

# Alpine uses addgroup/adduser instead of groupadd/useradd
RUN addgroup -S appgroup && adduser -S appuser -G appgroup

WORKDIR /app
COPY --chown=appuser:appgroup package.json package-lock.json ./
RUN npm ci --production
COPY --chown=appuser:appgroup . .

USER appuser
EXPOSE 3000
CMD ["node", "server.js"]
```

### Edge Cases

- **Binding to ports below 1024**: Non-root users cannot bind to privileged ports. Use ports above 1024 (e.g., 8000, 3000) and map them with Docker's `-p 80:8000`.
- **Writing to directories**: Ensure the user has write access to any directories the application needs (logs, uploads, cache). Create them before `USER` and set ownership with `chown`.
- **Pre-existing images**: For third-party images that run as root, override at runtime:

```bash
docker run --user 1000:1000 nginx:alpine
```

```yaml
# In Compose
services:
  nginx:
    image: nginx:alpine
    user: "1000:1000"
```

---

## Secrets Management

Never hardcode secrets in Dockerfiles, environment variables baked into images, or source code. Use one of these approaches.

### Docker Secrets (Compose / Swarm)

```yaml
services:
  app:
    image: myapp:latest
    secrets:
      - db_password
      - api_key
    environment:
      DB_PASSWORD_FILE: /run/secrets/db_password

secrets:
  db_password:
    file: ./secrets/db_password.txt
  api_key:
    environment: API_KEY_VAR
```

Application code reads the secret from the mounted file:

```python
from pathlib import Path

def get_secret(name: str) -> str:
    """Read a Docker secret from /run/secrets/."""
    secret_path = Path(f"/run/secrets/{name}")
    if secret_path.exists():
        return secret_path.read_text().strip()
    # Fall back to environment variable
    import os
    return os.environ[name.upper()]
```

### BuildKit Secret Mounts

For build-time secrets (e.g., private package registry credentials), use BuildKit secret mounts. The secret is never stored in any image layer.

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .

# Mount the secret at build time -- never persisted in a layer
RUN --mount=type=secret,id=pip_conf,target=/etc/pip.conf \
    pip install --no-cache-dir -r requirements.txt

COPY . .
CMD ["python", "server.py"]
```

```bash
docker build --secret id=pip_conf,src=$HOME/.pip/pip.conf -t myapp .
```

### What NOT to Do

```dockerfile
# WRONG: secret baked into image layer -- visible with docker history
ENV DATABASE_URL=postgres://user:password@host:5432/db

# WRONG: secret in build arg -- visible with docker inspect
ARG DB_PASSWORD
RUN echo "password=$DB_PASSWORD" > /app/config

# WRONG: copying secrets file into image
COPY .env /app/.env
```

---

## Image Scanning

Scan images for known vulnerabilities (CVEs) before deploying. Integrate scanning into CI/CD pipelines.

### Trivy

```bash
# Scan a local image
trivy image myapp:latest

# Scan and fail CI if HIGH or CRITICAL vulnerabilities found
trivy image --exit-code 1 --severity HIGH,CRITICAL myapp:latest

# Scan a Dockerfile for misconfigurations
trivy config Dockerfile

# Generate SBOM (Software Bill of Materials)
trivy image --format spdx-json -o sbom.json myapp:latest

# Scan with specific output format for CI
trivy image --format json --output results.json myapp:latest
```

### CI/CD Integration (GitHub Actions)

```yaml
- name: Build image
  run: docker build -t myapp:${{ github.sha }} .

- name: Scan image with Trivy
  uses: aquasecurity/trivy-action@master
  with:
    image-ref: myapp:${{ github.sha }}
    format: table
    exit-code: 1
    severity: HIGH,CRITICAL
    ignore-unfixed: true
```

Pin base image digests (not just tags) for reproducibility, scan base images separately, rebuild weekly to pick up patches, and use `--ignore-unfixed` to reduce noise.

---

## Read-Only Filesystems

Running containers with a read-only root filesystem prevents attackers from modifying binaries, installing tools, or writing malicious scripts.

```yaml
services:
  app:
    image: myapp:latest
    read_only: true
    tmpfs:
      - /tmp:size=50m
      - /app/cache:size=100m
    volumes:
      - app-data:/app/data      # Named volume for legitimate writes
    security_opt:
      - no-new-privileges:true
```

```bash
# Docker run equivalent
docker run --rm \
  --read-only \
  --tmpfs /tmp:size=50m \
  -v app-data:/app/data \
  --security-opt no-new-privileges \
  myapp:latest
```

### Handling Read-Only Edge Cases

Applications that need writable directories for PIDs, sockets, or caches:

```yaml
services:
  nginx:
    image: nginx:alpine
    read_only: true
    tmpfs:
      - /var/cache/nginx
      - /var/run
      - /tmp
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
```

---

## Capability Dropping

Linux capabilities give granular control over what the root user can do. Drop all capabilities and add back only what is needed.

```yaml
services:
  app:
    image: myapp:latest
    cap_drop:
      - ALL
    cap_add:
      - NET_BIND_SERVICE   # Only if binding to ports < 1024
    security_opt:
      - no-new-privileges:true
```

```bash
docker run --rm \
  --cap-drop ALL \
  --cap-add NET_BIND_SERVICE \
  --security-opt no-new-privileges \
  myapp:latest
```

### Common Capabilities

| Capability | Purpose |
|---|---|
| `NET_BIND_SERVICE` | Bind to ports below 1024 |
| `CHOWN` | Change file ownership |
| `SETUID` / `SETGID` | Change process UID/GID |
| `SYS_PTRACE` | Debug/trace processes (needed for some monitoring tools) |
| `DAC_OVERRIDE` | Bypass file permission checks |

Most applications need none of these. Start with `cap_drop: ALL` and add capabilities only when the application fails without them.

---

## Comprehensive Security Checklist

A hardened production Compose configuration should combine: read-only root filesystem with tmpfs for writable directories, non-root user for all services, all capabilities dropped with only essential ones re-added, `no-new-privileges` security option, resource limits, health checks, log rotation, Docker secrets for credentials, and internal networks for database tiers.
