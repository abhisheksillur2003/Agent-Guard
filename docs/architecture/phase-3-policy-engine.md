# Phase 3: deterministic policy engine

Phase 3 places a durable authorization decision between an authenticated agent and a requested tool operation. It does not execute the tool.

## Evaluation order

The gateway evaluates every request in this order:

1. Authenticate the agent credential and confirm that the agent is active.
2. Return a prior decision when the agent and idempotency key identify the same request hash.
3. Resolve the requested tool within the agent's organization.
4. Validate arguments against the tool's registered JSON Schema.
5. Require an explicit agent/tool permission for the operation and environment.
6. Load only active policies and their current immutable versions.
7. Match scope and evaluate typed conditions in priority order.
8. Give `deny` precedence over `require_approval`; otherwise return `allow`.
9. Commit the decision before returning it to the agent.

Any missing security dependency results in denial. Invalid stored policy data produces `POLICY_CONFIGURATION_INVALID`. A database failure prevents an allow response because the decision cannot be committed.

## Policy document

A policy version contains:

- A scope of optional agent IDs, tool IDs, environments, and operations. Empty scope lists are wildcards.
- An effect of `deny` or `require_approval`.
- A stable uppercase reason code.
- Conditions that all must match for the effect to trigger.

Supported conditions are:

- `field_missing` for a missing argument path.
- `number_gt` for numeric thresholds such as transaction limits.
- `value_in` for exact blocked values.
- `utc_hour_outside` for allowed UTC time windows, including windows that cross midnight.

An empty condition list makes the policy apply whenever its scope matches. Unknown policy fields and condition types are rejected instead of ignored.

## Versioning and precedence

Each policy starts at version 1. Supplying a new document increments the version and inserts a new row; existing version rows are never updated through the API. Metadata and activation status remain on the policy record.

Policies are evaluated by ascending priority and stable ID order. The first matching denial supplies the final reason code. If no denial matches, the first matching approval policy supplies the reason. Every matching policy version is retained as decision evidence.

## Decision storage

The `policy_decisions` table stores identity and request metadata, the request ID, SHA-256 hashes of the canonical request and arguments, the permission used, matched policy versions, every active version considered, sanitized evidence, and the final outcome. It never stores raw tool arguments.

The unique organization, agent, and idempotency-key constraint makes side-effect retries safe. A key is bound to the canonical request hash and cannot be reused for a different payload.

## Completion checks

Phase 3 is complete when tests prove:

1. Missing permissions and invalid arguments are durably denied.
2. Valid permitted requests are allowed when no restrictive policy matches.
3. Approval and denial policies match scope and conditions deterministically.
4. Denial takes precedence over approval.
5. Policy updates preserve earlier versions and disabled policies do not participate.
6. Invalid stored policy data fails closed.
7. Idempotent retries return one decision and conflicting reuse is rejected.
8. Raw arguments and invalid sensitive values do not appear in decision output or evidence.
9. The migration upgrades and downgrades successfully.
