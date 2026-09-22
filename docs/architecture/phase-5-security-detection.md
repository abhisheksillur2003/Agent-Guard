# Phase 5: deterministic security detection

Phase 5 inspects permitted, schema-valid tool arguments before policy evaluation. Its detectors provide deterministic evidence and enforcement for secrets, personally identifiable information, and prompt manipulation.

## Evaluation order

The complete authorization order is now:

1. Authenticate the agent and verify current status.
2. Resolve the tool within the agent's organization.
3. Validate arguments against the registered JSON Schema.
4. Require an explicit permission for the tool, operation, and environment.
5. Run every active, scoped detector at its current immutable version.
6. Evaluate active policy versions.
7. Give any detector or policy denial precedence over approval requirements.
8. Persist the decision, sanitized findings, and any required approval atomically.

Unauthorized or schema-invalid payloads are rejected before their content reaches the detector pipeline.

## Detector documents

Every version contains a scope, action, severity, reason code, kind, and kind-specific configuration. Empty scope lists are wildcards. Unknown fields and detector kinds are rejected instead of ignored.

Actions are:

- `record`: retain sanitized evidence without changing an otherwise allowed decision.
- `require_approval`: route the request into the Phase 4 approval workflow.
- `deny`: block the request.

Detector documents are immutable. Updating a document creates the next numbered version; disabling a detector changes status without rewriting history.

## Built-in detection

Secret detection supports AWS access-key identifiers, JWT-shaped tokens, private-key markers, common API-key formats, and configurable high-entropy token detection.

PII detection supports email addresses, phone numbers, Luhn-valid payment-card numbers, valid IPv4 addresses, and Indian Aadhaar-shaped identifiers. These deterministic recognizers favor predictable behavior. Presidio or spaCy can later add entity evidence without overriding deterministic denials.

Prompt-injection rules detect instruction replacement, requests to reveal system prompts, security or tool-control bypasses, and role impersonation. Input whitespace is normalized before matching so multiline phrases cannot bypass a rule.

## Data minimization

Matched values never enter a database row, API response, audit record, or log. Each finding stores:

- Detector and immutable version IDs
- Kind and category
- Severity and action
- Stable reason code
- Sanitized argument location
- Occurrence count
- HMAC-SHA-256 fingerprint using `AGENTGUARD_FINDING_FINGERPRINT_PEPPER`

The fingerprint permits correlation without making low-entropy PII vulnerable to an unkeyed hash lookup.

Scanning is limited to 200 string values, 100,000 characters, and ten nesting levels. Exceeding a bound creates a critical denial with `SECURITY_SCAN_LIMIT_EXCEEDED`.

## Execution consistency

Each Phase 3 decision records every active detector version considered. Phase 4 compares that set immediately before execution. Creating, updating, enabling, or disabling a detector invalidates an older unexecuted decision and requires a new evaluation.

## Completion checks

Phase 5 is complete when tests prove:

1. Detected secrets are denied without persisting the matched value.
2. Record-only PII findings allow an otherwise authorized request.
3. Prompt manipulation can require human approval.
4. Findings and detector configuration are tenant-scoped.
5. Detector updates preserve older versions and invalidate pending execution authority.
6. Disabled detectors do not participate.
7. Invalid detector configuration and exhausted scan budgets fail closed.
8. Multiline injection text cannot bypass whitespace-sensitive rules.
9. Migration upgrade and downgrade checks pass.
