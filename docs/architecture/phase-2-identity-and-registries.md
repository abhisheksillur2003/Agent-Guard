# Phase 2: identity and registries

Phase 2 establishes the identities and deterministic authorization data that later execution and policy phases will consume.

## Delivered capabilities

- Organizations isolate users, agents, tools, permissions, and audit history.
- Users authenticate with Argon2 password hashes and short-lived signed JWT access tokens.
- Roles are `admin`, `developer`, `approver`, and `read_only`; each route declares its accepted roles.
- Administrators can create users and manage their roles and status. The final active administrator cannot be demoted or disabled.
- Agents have explicit lifecycle state, allowed environments, a risk tier, and optional budgets.
- Agent API keys are generated with cryptographic randomness, shown once, and stored as an HMAC-SHA-256 digest using an application pepper.
- Rotating an agent key revokes all active keys in the same transaction. Suspended agents cannot authenticate.
- Tools carry a valid JSON Schema, risk class, capability flags, and lifecycle state.
- Permission grants connect one agent to one tool and list allowed operations plus deterministic constraints.
- Permission evaluation denies by default and returns stable reason codes.
- Security-relevant mutations create tenant-scoped audit records with request IDs and before/after hashes. Raw credentials and sensitive payloads are excluded.

## Trust boundaries

User JWT claims identify a candidate user and organization, but every request reloads the user from PostgreSQL and checks current status. Agent keys identify a credential prefix, then use constant-time digest comparison and verify credential expiry plus agent status. Route services always scope resource lookup by organization.

Permission evaluation requires all of the following: active agent, active tool, matching organization, allowed environment, an explicit agent/tool grant, and a listed operation. A missing dependency produces `PERMISSION_DENIED`.

## Database changes

Alembic revision `20260922_0002` creates `organizations`, `users`, `agents`, `agent_credentials`, `tools`, `agent_permissions`, and `audit_logs`. It includes foreign keys, uniqueness rules, state checks, query indexes, and a complete downgrade.

## Completion checks

Phase 2 is complete when:

1. An administrator can be bootstrapped, obtain a JWT, and manage organization users without exposing passwords.
2. Role restrictions reject unauthorized mutations.
3. Agent keys authenticate, rotate, expire, and stop working while the agent is suspended.
4. Tool JSON Schemas are validated before storage.
5. Missing or mismatched permission grants deny access.
6. Cross-organization lookups do not reveal resources.
7. Audit output never contains a generated credential.
8. Formatting, linting, static type checks, tests, and migration upgrade/downgrade checks pass.
