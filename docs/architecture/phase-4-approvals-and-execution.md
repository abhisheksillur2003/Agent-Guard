# Phase 4: approvals and controlled execution

Phase 4 converts Phase 3 decisions into a human approval workflow and a guarded adapter invocation. The implementation preserves the security order: authentication, schema validation, authorization, policy evaluation, durable decision, required approval, durable execution authorization, then adapter execution.

## Approval lifecycle

`require_approval` decisions create an approval row atomically with the decision. Approval states are `pending`, `approved`, `rejected`, `expired`, and `cancelled`.

Administrators and approvers can approve or reject. Only administrators can cancel. State changes lock the row, require a reason, reject repeated transitions, and create an audit event. Expiry is enforced whenever a request is read, listed, decided, or used for execution. An agent owner cannot decide its own agent's request.

The default approval lifetime is 24 hours and is configured with `AGENTGUARD_APPROVAL_TTL_HOURS`.

## Execution authorization

The agent that obtained the policy decision submits its decision ID and the original arguments. Raw arguments remain in request memory and are never persisted by AgentGuard.

Before execution, the service verifies:

1. The decision belongs to the authenticated agent and organization.
2. The SHA-256 argument hash matches the authorized request.
3. No execution already exists for the decision.
4. The decision is younger than `AGENTGUARD_EXECUTION_DECISION_TTL_MINUTES`.
5. The decision is not a denial.
6. The tool remains active, unchanged, and its JSON Schema still accepts the arguments.
7. The exact permission remains active and unchanged.
8. The active policy-version set matches the set evaluated for the decision.
9. A required approval exists and is approved.
10. The configured adapter name and version are registered.

Any mismatch requires a new Phase 3 evaluation. This makes policy, tool, and permission changes effective before a pending request can execute.

## Idempotency and crash behavior

Each decision can create only one execution. AgentGuard commits an `authorized` event, then commits a `running` event, before calling the adapter. Concurrent or later retries return the existing execution instead of invoking the adapter again.

If the process stops after the adapter side effect but before the terminal status commit, the stored execution remains `running`. A retry still does not re-execute it. Recovery and reconciliation of stranded runs can be added with the asynchronous worker phase.

## Adapter boundary

Adapters implement one asynchronous method that accepts validated in-memory arguments plus an execution context and returns a summary. The context includes a stable execution ID that adapters must propagate as the downstream idempotency key. Phase 4 includes only `safe_echo`, which reports argument field names and counts. Unknown adapters are rejected during tool registration.

Adapter calls have a database-configured timeout capped at 60 seconds. Results pass through a sanitizer that redacts credential-like keys, truncates strings and collections, and limits nesting. Exceptions produce stable error codes without persisting exception messages or request values.

## Execution states and events

The state model supports `authorized`, `queued`, `running`, `succeeded`, `failed`, `timed_out`, and `cancelled`. The current synchronous adapter path records:

1. `execution.authorized`
2. `execution.started`
3. One terminal success, failure, or timeout event

Events use unique sequence numbers and contain sanitized metadata only.

## Completion checks

Phase 4 is complete when tests prove:

1. Approval records are created for approval decisions.
2. Pending, rejected, expired, and cancelled requests cannot execute.
3. Agent owners cannot approve their own requests.
4. Approved and directly allowed decisions can execute exactly once.
5. Changed arguments, tools, permissions, or policies invalidate execution authority.
6. Execution events are ordered and durable before and after adapter invocation.
7. Timeouts and failures produce terminal states without leaking sensitive data.
8. Result sanitization redacts credential-like output.
9. The migration upgrades and downgrades successfully.
