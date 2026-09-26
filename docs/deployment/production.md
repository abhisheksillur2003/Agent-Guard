# Production deployment guide

## Prerequisites

Use a Linux server with a public IPv4 address, Docker Engine with the Compose plugin, at least 2 CPU cores, 4 GB RAM, and persistent disk. Point the domain's `A` record to the server. Add an `AAAA` record only when IPv6 is configured on the server. Allow inbound TCP 22 from trusted administration addresses, TCP 80 and 443 publicly, and UDP 443 publicly. Do not expose PostgreSQL, Redis, FastAPI, or metrics ports.

Clone a verified revision of the repository on the server. The examples below assume the repository root as the current directory.

## Secrets and configuration

Generate `.env.production` without printing its secrets:

```powershell
./scripts/prepare-production-env.ps1 `
  -Domain agentguard.example.com `
  -AcmeEmail admin@example.com
```

On Linux, restrict the file before deployment:

```bash
chmod 600 .env.production
```

Keep the file in an encrypted backup separate from the database backup. Losing the peppers prevents verification of existing agent credentials and consistent finding fingerprints. Changing the signing key immediately invalidates active user sessions.

## First deployment

Build from the checked-out source, validate configuration, apply migrations, and start the stack:

```powershell
./scripts/deploy-production.ps1
```

The script stops on invalid Compose configuration, failed image builds, or failed migrations. It never downgrades the database. Inspect status and logs with:

```powershell
docker compose --env-file .env.production -f docker-compose.production.yml ps
docker compose --env-file .env.production -f docker-compose.production.yml logs --tail 200 api frontend caddy worker scheduler
```

Create the first administrator interactively:

```powershell
docker compose --env-file .env.production -f docker-compose.production.yml exec api `
  agentguard-admin create-admin `
  --organization "AgentGuard Production" `
  --slug agentguard-production `
  --email admin@example.com
```

## Verification

Confirm all of the following from a computer outside the server:

- `https://your-domain/` redirects to the login page.
- `https://your-domain/healthz` returns HTTP 200 and reports `production`.
- `https://your-domain/readyz` returns HTTP 200.
- `https://your-domain/docs`, `/openapi.json`, and `/metrics` are not publicly available.
- Login succeeds and the session cookie is marked `Secure`, `HttpOnly`, and `SameSite=Lax`.
- PostgreSQL and Redis ports cannot be reached from the internet.
- A tool request still passes authentication, schema validation, authorization, policy evaluation, and durable recording before execution.

Run a TLS configuration scan after DNS and certificate issuance. Keep server time synchronized because authentication tokens and approval expiry depend on accurate UTC time.

## Published container images

After CI succeeds on `main`, GitHub Actions publishes:

- `ghcr.io/abhisheksillur2003/agentguard-api:sha-<commit>`
- `ghcr.io/abhisheksillur2003/agentguard-frontend:sha-<commit>`

Set `AGENTGUARD_API_IMAGE` and `AGENTGUARD_FRONTEND_IMAGE` in `.env.production` to immutable SHA tags. Authenticate the server to GHCR if the packages are private, then deploy without rebuilding:

```powershell
./scripts/deploy-production.ps1 -SkipBuild
```

## Backups

Create encrypted off-server PostgreSQL backups on a schedule. A logical backup can be produced with:

```bash
docker compose --env-file .env.production -f docker-compose.production.yml exec -T postgres \
  pg_dump --format=custom --no-owner --username agentguard agentguard > agentguard-$(date +%F).dump
```

Test restoration regularly on a separate database. Back up `.env.production` separately; do not store it in the container image, repository, or database dump. Redis contains maintenance queue state and is not authoritative.

## Updates and rollback

Before updating, record the deployed Git commit and image SHA tags, take a database backup, fetch the reviewed revision, and run the deployment script. Review every Alembic migration and its downgrade before applying it.

Application rollback uses the previous immutable API and frontend image tags. Database rollback is a separate operation: perform it only after reviewing data-safety implications and confirming the older application cannot run against the newer schema. Never automatically downgrade a production database.

## Local AI and observability

The production template disables local AI. Enable it only when Ollama is hosted on a private authenticated network and its resource use, privacy boundary, availability, and patching are managed explicitly. Its output remains advisory.

The local Grafana stack is not exposed by this deployment. Send OTLP traces to a private collector by setting `AGENTGUARD_OTEL_TRACES_ENDPOINT`, and configure an internal Prometheus scraper for `http://api:8000/metrics`. Do not route `/metrics` through the public gateway.

## Outbound webhook connector

The production template disables outbound webhooks. To enable `http_webhook@1`, add an exact HTTPS URL to `AGENTGUARD_HTTP_WEBHOOK_ALLOWED_URLS`, set `AGENTGUARD_HTTP_WEBHOOK_ENABLED=true`, and optionally add a bearer token keyed by the same URL in `AGENTGUARD_HTTP_WEBHOOK_BEARER_TOKENS`. Keep tokens only in the protected environment file. The API refuses production HTTP URLs, placeholder tokens, URL credentials, query-string secrets, and token entries that do not match the allowlist.

Keep `AGENTGUARD_HTTP_WEBHOOK_ALLOW_PRIVATE_NETWORKS=false` for internet-facing receivers. Enable it only for a reviewed internal destination reachable through the container network, then verify firewall and DNS behavior independently. See [`../architecture/phase-11-http-webhook.md`](../architecture/phase-11-http-webhook.md) for the execution contract and failure codes.
