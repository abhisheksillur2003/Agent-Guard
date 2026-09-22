# AgentGuard repository guidance

## Project intent

AgentGuard is a security, reliability, and observability control plane for tool-using AI agents. Security-sensitive decisions must be deterministic, explainable, versioned, and deny by default.

## Supported toolchain

- Python 3.13 only.
- Use `uv` for Python dependency and environment management.
- Use Docker Compose for infrastructure services.
- Never commit `.env`, credentials, tokens, generated secrets, or sensitive example data.

## Canonical commands

- Install: `uv sync --all-groups`
- Start PostgreSQL: `docker compose up -d postgres`
- Apply migrations: `uv run alembic upgrade head`
- Run API: `uv run uvicorn backend.app.main:app --reload`
- Format check: `uv run ruff format --check .`
- Lint: `uv run ruff check .`
- Type check: `uv run pyright`
- Test: `uv run pytest`
- Full local verification: run format check, lint, type check, tests, and migration smoke tests.

## Engineering rules

- Keep HTTP handlers thin; place domain behavior in dedicated services as the project grows.
- Validate all external input with typed schemas.
- Treat agent identity, requested environment, tool name, and request context as untrusted input.
- Default to denial when authentication, permissions, policies, or required security dependencies cannot produce a trustworthy result.
- Deterministic permission and policy denials must never be overridden by probabilistic or model-generated output.
- Never log credentials, secrets, raw sensitive payloads, or unmasked security evidence.
- Every schema change requires an Alembic migration with a working downgrade.
- Add meaningful tests for new behavior; do not weaken tests to make a change pass.
- Do not add production dependencies unless a current requirement needs them.
- Preserve API compatibility unless the task explicitly changes the contract.

## Completion report

At task completion, report files changed, verification commands run, results, and unresolved risks or prerequisites.

## Code Review Rules

- Flag any path that permits tool execution before authentication, schema validation, authorization, policy evaluation, and durable decision recording.
- Flag fail-open behavior in security-critical paths. The safe path is an explicit denial or a documented degraded mode limited to low-impact operations.
- Flag storage or logging of plaintext credentials and sensitive payloads. Use one-way hashes for credentials and sanitized structured evidence for logs.
- Flag migrations without a downgrade or data-safety explanation.
- Flag retry behavior that can duplicate side effects; require idempotency for side-effecting operations.

