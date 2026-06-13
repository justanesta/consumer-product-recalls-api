# Networking and Volumes Reference

Detailed patterns for Docker networking drivers, volume types, data persistence strategies, and container communication for development and production environments.

---

## Network Drivers

Docker provides several network drivers. The choice depends on whether containers run on a single host or across a cluster.

### Driver Overview

| Driver | Scope | Use Case |
|---|---|---|
| `bridge` | Single host | Default. Containers communicate via internal DNS. |
| `host` | Single host | Container shares host network stack. No port mapping needed. |
| `overlay` | Multi-host (Swarm) | Cross-host communication in Docker Swarm or Kubernetes. |
| `macvlan` | Single host | Container gets its own MAC address on the physical network. |
| `none` | Single host | No networking. Fully isolated container. |

### Bridge Networks

Bridge is the default driver. User-defined bridge networks provide automatic DNS resolution between containers by service name.

```yaml
services:
  api:
    build: .
    ports:
      - "8000:8000"
    networks:
      - frontend
      - backend

  db:
    image: postgres:16-alpine
    networks:
      - backend

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    networks:
      - frontend

networks:
  frontend:
    driver: bridge
  backend:
    driver: bridge
    internal: true   # No external access -- only inter-container traffic
```

Key behaviors:
- Containers on the same user-defined bridge can reach each other by service name (`http://api:8000`).
- The default bridge network does NOT provide DNS resolution -- always create named networks.
- `internal: true` blocks outbound internet access from the network, useful for database tiers.

### Host Networking

Host mode removes network isolation. The container shares the host's IP and ports directly. Useful for performance-sensitive applications that need to avoid NAT overhead.

```yaml
services:
  monitoring:
    image: prom/node-exporter
    network_mode: host
    pid: host
```

Note: `ports:` mapping is ignored in host mode, and port conflicts will prevent the container from starting.

### Overlay Networks

Overlay networks span multiple Docker hosts in a Swarm cluster. Traffic is encrypted when the `--opt encrypted` flag is set.

```bash
# Create an encrypted overlay network
docker network create \
  --driver overlay \
  --opt encrypted \
  --attachable \
  my-overlay
```

```yaml
# docker-compose.yml for Swarm deployment
services:
  web:
    image: myapp:latest
    deploy:
      replicas: 3
    networks:
      - app-net

networks:
  app-net:
    driver: overlay
    attachable: true
```

---

## Named Volumes

Named volumes are managed by Docker and persist across container restarts and removals. They are the recommended way to store persistent data.

```yaml
services:
  db:
    image: postgres:16-alpine
    volumes:
      - pgdata:/var/lib/postgresql/data

  app:
    build: .
    volumes:
      - uploads:/app/uploads

volumes:
  pgdata:
    driver: local
  uploads:
    driver: local
    driver_opts:
      type: none
      device: /data/uploads
      o: bind
```

### Volume Lifecycle

```bash
# List all volumes
docker volume ls

# Inspect a volume (shows mount point on host)
docker volume inspect myproject_pgdata

# Remove unused volumes (not attached to any container)
docker volume prune

# Remove a specific volume (container must be stopped and removed first)
docker volume rm myproject_pgdata

# Back up a volume
docker run --rm \
  -v myproject_pgdata:/source:ro \
  -v $(pwd):/backup \
  alpine tar czf /backup/pgdata-backup.tar.gz -C /source .

# Restore a volume
docker run --rm \
  -v myproject_pgdata:/target \
  -v $(pwd):/backup \
  alpine tar xzf /backup/pgdata-backup.tar.gz -C /target
```

### Volume Permissions

A common issue: the container process runs as a non-root user but the volume directory is owned by root.

```dockerfile
FROM python:3.12-slim
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Create the mount point with correct ownership BEFORE declaring VOLUME
RUN mkdir -p /app/data && chown appuser:appuser /app/data

USER appuser
WORKDIR /app
```

If the volume is already populated, fix permissions from outside:

```bash
docker run --rm -v myproject_data:/data alpine chown -R 1000:1000 /data
```

---

## Bind Mounts

Bind mounts map a host directory directly into the container. They are ideal for development (live code reloading) but should be avoided in production.

```yaml
services:
  app:
    build: .
    volumes:
      # Source code for live reloading
      - ./src:/app/src
      # Config file, read-only
      - ./config/app.yaml:/app/config.yaml:ro
      # Prevent host node_modules from overriding container's
      - /app/node_modules
```

Bind mount flags: `:ro` for read-only, `:cached` for relaxed consistency on macOS, `:delegated` for fastest macOS writes, and `:consistent` (default) for full consistency.

### Development vs Production Pattern

```yaml
# docker-compose.override.yml (development)
services:
  app:
    volumes:
      - .:/app                    # Bind mount for live reload
      - /app/node_modules         # Anonymous volume to protect container deps
    command: npm run dev

# docker-compose.prod.yml (production)
services:
  app:
    # No bind mounts -- source code is baked into the image
    volumes:
      - app-uploads:/app/uploads  # Only named volumes for persistent data
```

---

## tmpfs Mounts

tmpfs mounts store data in memory. Data disappears when the container stops. Use tmpfs for scratch space, caches, or sensitive data that should not persist to disk.

```yaml
services:
  app:
    image: myapp:latest
    tmpfs:
      - /tmp
      - /app/cache:size=100m

```

Use tmpfs for session storage, temporary build artifacts, sensitive decrypted data, and `/tmp` to prevent filling the writable layer.

```yaml
services:
  app:
    image: myapp:latest
    read_only: true         # Read-only root filesystem
    tmpfs:
      - /tmp                # Writable temp directory in RAM
      - /app/cache          # Writable cache directory in RAM
    volumes:
      - app-data:/app/data  # Named volume for persistent data
```

---

## Container-to-Container Communication

### Service Discovery

On a user-defined bridge network, containers resolve each other by service name.

```python
# Inside the "app" container, connect to the "db" service
import psycopg2

conn = psycopg2.connect(
    host="db",          # Service name from docker-compose.yml
    port=5432,
    database="mydb",
    user="app",
    password="secret"
)
```

### Isolating Tiers

```yaml
services:
  nginx:
    networks: [frontend]

  api:
    networks: [frontend, backend]

  db:
    networks: [backend]

  cache:
    networks: [backend]

networks:
  frontend:
  backend:
    internal: true
```

With this layout:
- `nginx` can reach `api` but NOT `db` or `cache`.
- `api` can reach both `nginx` and `db`/`cache`.
- `db` and `cache` cannot reach the internet (`internal: true`).
