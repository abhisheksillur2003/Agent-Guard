# Phase 15: local demo workspace

Phase 15 makes the complete AgentGuard security flow usable on one Windows workstation without a cloud account. An idempotent administrative command creates synthetic, local-only resources through the same domain services used by the API.

## Seeded resources

`agentguard-admin seed-local-demo` creates:

- One active `Local Support Agent` restricted to the `local` environment.
- One `Local Refund Simulator` tool backed by the side-effect-free `safe_echo@1` adapter.
- One explicit `refund` permission from that agent to that tool.
- One policy requiring approval for refund amounts greater than 500.
- A secret detector that denies credential-shaped content.
- A PII detector that records sanitized evidence without storing matched values.
- A prompt-manipulation detector that requires human review.
- Optionally, one agent credential that is displayed once and stored only as a keyed hash.

The command requires an existing active administrator. It refuses every environment except `local`. It does not create external connections, send webhooks, or enable the production connector.

## Idempotency and conflicts

Running the command repeatedly does not duplicate resources or rotate an existing credential. Existing resources with the reserved demo names must match the expected active configuration; otherwise, the command stops with an explicit conflict instead of rewriting operator-managed data.

Use `--skip-credential` when the goal is only to populate the browser dashboard. A credential can be issued later from the Agents page.

## Demonstrated outcomes

The synthetic refund workflow provides three deterministic examples:

1. An amount of 500 or less passes when its content is clean.
2. An amount greater than 500 requires approval.
3. Credential-shaped content is denied before policy evaluation.

No raw arguments, secrets, or PII values are persisted by the decision or finding records.

## Completion checks

Phase 15 is complete when automated tests prove that bootstrap is idempotent, credentials are not stored in plaintext, the allow path executes through `safe_echo`, large refunds require approval, secret-shaped input is denied without disclosure, and non-local environments fail closed.
