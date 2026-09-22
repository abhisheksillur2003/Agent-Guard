# ADR 0001: Local-first PostgreSQL foundation

- Status: Accepted
- Date: 2026-09-22

## Context

AgentGuard needs transactional state for decisions, approvals, audit indexes, and eventual idempotent tool execution. The portfolio MVP must remain reproducible without paid infrastructure.

## Decision

Use PostgreSQL as the source of truth and run it through Docker Compose for local development. Use SQLAlchemy's asynchronous API and Alembic for every schema change. Keep application startup independent from database connectivity, expose dependency status through `/readyz`, and fail readiness when the database is unavailable.

## Consequences

- Local development needs Docker Desktop or another compatible Docker engine.
- CI can verify real PostgreSQL migrations rather than relying on a different test database.
- Phase 2 domain models can be introduced through reversible migrations.
- The application remains observable during database outages but must not serve stateful business operations until readiness succeeds.

