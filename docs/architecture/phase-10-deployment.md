# Phase 10: production deployment

Phase 10 packages AgentGuard as a production-oriented single-host stack. It separates the public gateway, frontend, API, maintenance processes, broker, and authoritative database while preserving the same application contracts used locally.

## Runtime topology

```text
Internet
   |
   v
Caddy :80/:443  -- automatic TLS and security headers
   |                         |
   v                         v
Next.js :3000             FastAPI :8000
   |                         |  |
   +------ internal API -----+  +---- PostgreSQL
                                +---- Redis
                                       |
                                 Celery worker + scheduler
```

Caddy publishes only the Next.js application, `/api/v1/*`, `/healthz`, and `/readyz`. `/metrics`, PostgreSQL, Redis, FastAPI documentation, and container service ports are not exposed publicly. Next.js keeps user access tokens in secure, HttpOnly, same-site cookies and reaches FastAPI over the private Compose network.

## Container controls

- The API, worker, scheduler, migration, and frontend containers run as non-root users.
- Application filesystems are read-only with bounded temporary filesystems.
- Linux capabilities are dropped and privilege escalation is disabled.
- PostgreSQL data and Caddy certificates use named volumes.
- API readiness checks PostgreSQL before traffic is accepted.
- Database migrations run as an explicit one-shot step before services are replaced.
- Caddy terminates TLS and adds HSTS, framing, MIME sniffing, referrer, and browser-permission headers.
- Base images and GitHub Actions are pinned to reviewed immutable revisions.

## Production configuration

The application refuses to start in `production` when API documentation is enabled, allowed hosts contain a wildcard, the database uses the local default password, security secrets are short or placeholders, or security secrets are reused. Local AI is disabled in the production template because a workstation Ollama process is not reachable or protected as a production dependency.

The generated `.env.production` file is ignored by Git. It contains independent URL-safe values for the PostgreSQL password, Redis password, token signing key, agent credential pepper, and finding fingerprint pepper.

## Delivery

The `Publish containers` GitHub workflow runs only after the main CI workflow succeeds. It builds both Dockerfiles, emits software bills of materials and build provenance, and publishes `latest` and commit-SHA tags to GitHub Container Registry. Deployment may build directly from a verified checkout or use the immutable SHA tags.
