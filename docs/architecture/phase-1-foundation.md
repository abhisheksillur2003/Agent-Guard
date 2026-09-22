# Phase 1 foundation

## Purpose

Phase 1 establishes a small, reproducible backend foundation without implementing AgentGuard's security-domain behavior prematurely.

## Runtime shape

```text
Client
  |
  v
FastAPI  ---> PostgreSQL
  |
  +---- structured process logs
```

The API starts independently of PostgreSQL so liveness remains observable during dependency outages. Readiness fails until PostgreSQL can answer a minimal query.

## Included

- FastAPI application factory
- Request correlation IDs
- JSON process logging
- Typed environment configuration
- Asynchronous PostgreSQL engine
- Alembic migration baseline
- Docker Compose PostgreSQL service
- Backend unit tests
- CI quality and migration checks

## Deferred deliberately

- Domain tables and authentication
- Redis and background jobs
- Policy, security, risk, approval, and execution engines
- Frontend application
- OpenTelemetry, Prometheus, and Grafana
- Local model integration

Each deferred capability must enter the repository with a requirement, acceptance criteria, and meaningful tests.

