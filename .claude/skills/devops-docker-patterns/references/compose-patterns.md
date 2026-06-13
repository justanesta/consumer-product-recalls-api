# Docker Compose Patterns Reference

Detailed patterns for Docker Compose service orchestration, covering service definitions, health checks, profiles, override files, environment management, and production configurations.

---

## Service Definitions

A Compose file declares services, networks, and volumes. Each service maps to one container.

### Full-Stack Application

```yaml
services:
  web:
    build:
      context: .
      dockerfile: Dockerfile
      target: production
      args:
        NODE_ENV: production
    ports:
      - "3000:3000"
    environment:
      - DATABASE_URL=postgres://app:secret@db:5432/mydb
      - REDIS_URL=redis://cache:6379/0
    depends_on:
      db:
        condition: service_healthy
      cache:
        condition: service_started
    restart: unless-stopped
    networks:
      - frontend
      - backend

  db:
    image: postgres:16-alpine
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    environment:
      POSTGRES_USER: app
      POSTGRES_PASSWORD: secret
      POSTGRES_DB: mydb
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app -d mydb"]
      interval: 5s
      timeout: 3s
      retries: 5
      start_period: 10s
    networks:
      - backend

  cache:
    image: redis:7-alpine
    command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru
    volumes:
      - redis-data:/data
    networks:
      - backend

volumes:
  pgdata:
  redis-data:

networks:
  frontend:
  backend:
```

---

## depends_on and Health Checks

`depends_on` controls startup order. Without a `condition`, Compose only waits for the container to start, not for the service to be ready.

### Health Check Patterns for Common Services

```yaml
services:
  postgres:
    image: postgres:16-alpine
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER}"]
      interval: 5s
      timeout: 3s
      retries: 5
      start_period: 10s

  elasticsearch:
    image: elasticsearch:8.12.0
    healthcheck:
      test: ["CMD-SHELL", "curl -fsSL http://localhost:9200/_cluster/health || exit 1"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 30s

  app:
    build: .
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      elasticsearch:
        condition: service_healthy
```

### Edge Cases

- `depends_on` only affects startup order. If a service crashes later, dependents are not restarted.
- `restart: unless-stopped` handles transient failures but is not a substitute for proper health checks.
- `start_period` gives slow-starting services (like Elasticsearch or Java apps) time to initialize before health checks count as failures.

---

## Profiles

Profiles let you define services that only start when explicitly activated. This is useful for separating development tools from production services.

```yaml
services:
  app:
    build: .
    ports:
      - "8000:8000"

  db:
    image: postgres:16-alpine

  # Only starts with: docker compose --profile debug up
  adminer:
    image: adminer
    ports:
      - "8080:8080"
    profiles:
      - debug

  test-runner:
    build:
      context: .
      target: test
    command: pytest
    profiles:
      - test
```

```bash
# Start only core services
docker compose up

# Start core + monitoring
docker compose --profile monitoring up

# Start core + debug + monitoring
docker compose --profile debug --profile monitoring up

# Run tests then exit
docker compose --profile test run --rm test-runner
```

---

## Override Files

Compose automatically merges `docker-compose.yml` with `docker-compose.override.yml`. Use this for development-specific settings.

### docker-compose.yml (base -- used everywhere)

```yaml
services:
  app:
    build:
      context: .
      target: production
    ports:
      - "8000:8000"
    environment:
      - APP_ENV=production

  db:
    image: postgres:16-alpine
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

### docker-compose.override.yml (development -- auto-loaded)

```yaml
services:
  app:
    build:
      target: development
    volumes:
      - .:/app
      - /app/node_modules
    environment:
      - APP_ENV=development
      - DEBUG=true
    command: npm run dev

  db:
    ports:
      - "5432:5432"
    environment:
      POSTGRES_PASSWORD: devpassword
```

### docker-compose.prod.yml (production -- explicit)

```yaml
services:
  app:
    image: registry.example.com/myapp:${TAG:-latest}
    deploy:
      replicas: 3
      resources:
        limits:
          cpus: "1.0"
          memory: 512M
    restart: always
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "5"

  db:
    environment:
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    secrets:
      - db_password

secrets:
  db_password:
    file: ./secrets/db_password.txt
```

```bash
# Development (uses override automatically)
docker compose up

# Production (skip override, use prod file)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# CI/CD
docker compose -f docker-compose.yml -f docker-compose.ci.yml run --rm test
```

---

## Environment Management

### Environment File

```yaml
services:
  app:
    env_file:
      - .env
      - .env.local   # Overrides values in .env
    environment:
      - APP_ENV=production   # Overrides values from env_file
```

### Variable Substitution

Compose supports shell-style variable substitution with defaults.

```yaml
services:
  app:
    image: myapp:${TAG:-latest}           # Default to "latest" if TAG is unset
    ports:
      - "${HOST_PORT:-8000}:8000"
    environment:
      - LOG_LEVEL=${LOG_LEVEL:?LOG_LEVEL must be set}  # Error if unset
```

---

## Resource Limits and Restart Policies

Set `deploy.resources.limits` to cap CPU and memory. Use `restart: unless-stopped` for automatic recovery from crashes. Under `deploy`, `restart_policy` adds backoff and attempt limits for finer control.
