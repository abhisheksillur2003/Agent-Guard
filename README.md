# AgentGuard

AgentGuard is a local-first security, reliability, and observability control plane for tool-using AI agents. Phase 1 provides the typed FastAPI and PostgreSQL foundation. Phase 2 adds tenant-scoped identities, registries, permissions, and audit records. Phase 3 adds immutable policy versions and a durable, deny-by-default decision gateway. Phase 4 adds human approvals and controlled, idempotent tool execution. Phase 5 adds deterministic secret, PII, and prompt-injection protection. Phase 6 adds rate limits, execution budgets, loop detection, bounded retries, and background reconciliation. Phase 7 adds the authenticated Next.js operations console. Phase 8 adds privacy-safe metrics, traces, and local monitoring dashboards.

## Prerequisites

- Python 3.13
- [uv](https://docs.astral.sh/uv/)
- Docker Desktop with Docker Compose
- Git
- Node.js 24 LTS
- pnpm 11

## Local setup

```powershell
Copy-Item .env.example .env
uv sync --all-groups
docker compose up -d postgres redis
uv run alembic upgrade head
uv run agentguard-admin create-admin --organization "AgentGuard Local" --slug agentguard-local --email admin@example.com
uv run uvicorn backend.app.main:app --reload
pnpm --dir frontend install --frozen-lockfile
pnpm --dir frontend dev
```

The administrator command prompts for a password without echoing it. Use at least 12 characters. Set independent random values for `AGENTGUARD_AUTH_SIGNING_KEY` and `AGENTGUARD_AGENT_KEY_PEPPER` before using the service outside disposable local development.

The API will be available at `http://127.0.0.1:8000`. The frontend will be available at `http://127.0.0.1:3000`.

- Liveness: `GET /healthz`
- Readiness: `GET /readyz`
- OpenAPI: `GET /docs`
- Prometheus metrics: `GET /metrics`

`/healthz` reports whether the API process is alive. `/readyz` verifies that PostgreSQL is reachable and returns HTTP 503 when it is not.

## Phase 2 API

Obtain a user access token with the administrator email and password:

```powershell
$token = (Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/auth/token `
  -ContentType "application/x-www-form-urlencoded" `
  -Body @{ username = "admin@example.com"; password = "your-password" }).access_token

$headers = @{ Authorization = "Bearer $token" }
Invoke-RestMethod http://127.0.0.1:8000/api/v1/auth/me -Headers $headers
```

The OpenAPI page documents the full contract. The main Phase 2 routes are:

- `POST /api/v1/auth/token`, `GET /api/v1/auth/me`, and `GET /api/v1/auth/agent/me`
- `GET /api/v1/organization`
- Administrator-only user creation and role/status management under `/api/v1/users`
- CRUD-style registration and lifecycle routes under `/api/v1/agents`
- Agent credential creation and rotation under `/api/v1/agents/{agent_id}/credentials`
- Tool registration routes under `/api/v1/tools`
- Permission grants under `/api/v1/agents/{agent_id}/permissions`
- Tenant-scoped audit history at `GET /api/v1/audit`

Agent credentials are displayed once, stored only as keyed hashes, and invalidated when rotated. Permission checks deny access when an identity, resource, environment, operation, or grant does not match.

## Phase 3 policy gateway

Administrators manage versioned policies under `/api/v1/policies`. Updating a policy document creates a new immutable version; changing metadata or status does not rewrite previous versions. Policy effects are `deny` and `require_approval`. An explicit permission plus no matching restrictive policy produces `allow`.

An authenticated agent evaluates a tool request with:

```http
POST /api/v1/tool-requests/evaluate
Authorization: Bearer agk_...
Content-Type: application/json

{
  "tool_id": "00000000-0000-0000-0000-000000000000",
  "operation": "refund",
  "environment": "production",
  "arguments": {"order_id": "ORD-123", "amount": 1200},
  "idempotency_key": "refund-ORD-123-attempt-1"
}
```

The gateway validates the registered tool schema, checks the explicit agent permission, evaluates active policy versions, and commits the final `allow`, `deny`, or `require_approval` decision before responding. Raw arguments are hashed rather than stored. Reusing an idempotency key with the same request returns the original decision; reusing it with a different request returns HTTP 409.

Authorized users can inspect tenant-scoped decisions at `GET /api/v1/tool-requests/decisions`. A `require_approval` outcome feeds the Phase 4 approval workflow described below.

## Phase 4 approvals and execution

A `require_approval` decision now creates a pending approval request in the same transaction. Administrators and approvers can inspect and decide requests under `/api/v1/approvals`. An agent owner cannot decide its own agent's request, and expired or previously decided approvals cannot transition again.

After an `allow` decision, or after the required approval, the same authenticated agent submits the original arguments:

```http
POST /api/v1/executions
Authorization: Bearer agk_...
Content-Type: application/json

{
  "decision_id": "00000000-0000-0000-0000-000000000000",
  "arguments": {"order_id": "ORD-123", "amount": 1200}
}
```

Before invoking an adapter, AgentGuard verifies the argument hash, decision age, tool schema and status, permission record, current policy-version set, and approval status. It commits `authorized` and `running` states before execution. A unique decision constraint prevents a retry from invoking the adapter twice.

Phase 4 ships only the `safe_echo` adapter. It returns the execution ID plus argument field names and counts without returning values. Additional adapters must be registered in code, propagate the execution ID as their downstream idempotency key, and satisfy the same bounded, sanitized interface; tool registration rejects unknown adapters.

Users can inspect runs and ordered events through:

- `GET /api/v1/executions`
- `GET /api/v1/executions/{execution_id}`
- `GET /api/v1/executions/{execution_id}/events`

## Phase 5 security detectors

Administrators configure immutable, versioned detectors under `/api/v1/security/detectors`. Detector documents use a tenant-scoped combination of agent IDs, tool IDs, environments, and operations. Each detector chooses `record`, `require_approval`, or `deny`, plus a stable reason code and severity.

Built-in deterministic checks support:

- Secrets: AWS access keys, JWTs, private-key markers, common API-key formats, and high-entropy tokens
- PII: email addresses, phone numbers, Luhn-valid payment-card numbers, IPv4 addresses, and Indian Aadhaar-shaped identifiers
- Prompt manipulation: instruction replacement, system-prompt extraction, security/tool override, and role impersonation phrases

Scanning runs after schema and permission checks but before policy evaluation. Findings store a keyed fingerprint, category, sanitized argument location, severity, action, and occurrence count. Matched text is never persisted or returned. Oversized or excessively nested scan input fails closed.

Security teams can inspect findings through:

- `GET /api/v1/security/findings`
- `GET /api/v1/security/findings/{finding_id}`

Detector version changes invalidate pending execution authority, forcing the agent to evaluate the request again.

## Phase 6 reliability controls

Every agent has a validated `budget_config` with secure defaults for decisions per minute, executions per day, repeated-request detection, retry attempts, and retry backoff. PostgreSQL is the authoritative counter store. Agent evaluations take a transaction-scoped advisory lock, so concurrent requests cannot race through the same limit. A reliability denial is saved as a normal policy decision with a stable reason code and sanitized counter evidence.

Failed or timed-out executions may be retried through `POST /api/v1/executions/{execution_id}/retry` only when the agent budget permits another attempt and the adapter explicitly supports idempotent retries. The retry must provide arguments matching the original hash. Every attempt uses the original execution ID as its downstream idempotency key and records ordered events.

Redis is the Celery broker for periodic maintenance tasks. The worker carries no tool arguments or sensitive payloads. It expires overdue approvals and marks executions left `running` after a process loss as failed. On Windows, run the worker and scheduler in separate terminals:

```powershell
uv run celery -A backend.app.worker:celery_app worker --pool=solo --loglevel=INFO
uv run celery -A backend.app.worker:celery_app beat --loglevel=INFO
```

## Phase 8 observability

Start the local monitoring profile, then restart FastAPI with the OTLP endpoint from `.env`:

```powershell
docker compose --profile observability up -d
uv run uvicorn backend.app.main:app --reload
```

Prometheus scrapes privacy-safe API metrics from `/metrics`. Open Grafana at `http://127.0.0.1:3001` for the provisioned AgentGuard dashboard, Prometheus at `http://127.0.0.1:9090`, and Tempo at `http://127.0.0.1:3200` for trace storage. Monitoring ports bind to localhost. The dashboard stack is optional and uses only open-source local services.

## Verification

```powershell
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run pytest
uv run alembic heads
pnpm --dir frontend format:check
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend build
```

With PostgreSQL running, verify migrations in both directions:

```powershell
uv run alembic upgrade head
uv run alembic downgrade base
uv run alembic upgrade head
```

## Repository layout

```text
backend/
  alembic/              Database migrations
  app/
    api/                HTTP routes
    core/               Configuration and logging
    db/                 Database engine and metadata
    main.py             FastAPI application factory
  tests/                Backend tests
docs/
  adr/                   Architecture decision records
  architecture/          Current architecture notes
evals/                   Future security evaluation corpus
frontend/                Next.js operations console
scripts/                 Repository automation
```

## Current scope

Phases 1 through 8 are complete. Production tool integrations and optional local-model classification remain future phases.

## Security posture

AgentGuard will use deterministic permissions and policies as the final authority for security-critical decisions. Model-generated classifications may add evidence later, but they will not override access-control denials.
