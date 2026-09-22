# Phase 6: reliability controls

Phase 6 prevents an otherwise authorized agent from consuming resources without bounds or repeating the same action indefinitely. These controls are deterministic and run before policy evaluation grants authority.

## Agent reliability profile

The existing `budget_config` field now accepts a strict, typed profile:

- decisions per rolling minute
- executions per UTC day
- identical requests within a bounded loop-detection window
- maximum attempts per execution
- minimum delay before a retry

Unknown fields, non-positive limits, and out-of-range values are rejected at the API. Invalid data discovered in storage produces `RELIABILITY_CONFIGURATION_INVALID` and a durable denial.

PostgreSQL remains authoritative for counters. Evaluation takes a transaction-scoped advisory lock derived from the agent ID before reading counters and writing a decision. This serializes concurrent requests for one agent without blocking unrelated agents.

## Deny reasons

- `RATE_LIMIT_EXCEEDED`
- `REQUEST_LOOP_DETECTED`
- `DAILY_EXECUTION_BUDGET_EXCEEDED`
- `RELIABILITY_CONFIGURATION_INVALID`

Decision evidence contains the normalized limits, observed counts, and a profile hash. It contains no raw tool arguments. Execution compares the current profile hash with the decision snapshot, so changing a limit invalidates older unexecuted authority.

## Controlled retries

Retries are explicit and bounded. They require:

1. a failed or timed-out execution;
2. unchanged arguments matching the original authorization hash;
3. an unexpired and still-valid decision, permission, policy, detector, and reliability profile;
4. remaining attempts and an elapsed backoff window; and
5. an adapter that explicitly declares idempotent retry support.

All attempts reuse the execution ID as the downstream idempotency key. Attempt count and ordered events are durable. A successful execution cannot be retried.

## Background recovery

Redis acts only as the Celery broker. Periodic tasks carry identifiers and maintenance instructions, never raw tool arguments. The worker expires overdue approvals and reconciles executions stranded in `running` after process loss. Reconciliation records a terminal event and an audit record with `EXECUTION_WORKER_LOST`.

The API's authorization and reliability decisions do not depend on Redis. If Redis or the worker is unavailable, maintenance is delayed while the request path continues to use PostgreSQL. This avoids a cache failure changing an allow or deny result.

## Completion criteria

Phase 6 is complete when tests prove:

1. rate, daily execution, and repeated-request limits deny at their boundaries;
2. malformed stored reliability configuration fails closed;
3. a retry is bounded, requires matching arguments, and reuses one execution ID;
4. attempt events remain ordered and durable; and
5. reconciliation closes a stranded execution without invoking its adapter again.
