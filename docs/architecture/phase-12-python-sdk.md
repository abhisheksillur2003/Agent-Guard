# Phase 12: Python agent SDK

Phase 12 provides an asynchronous Python client that keeps AI-generated tool actions behind AgentGuard's deterministic control plane. The SDK never runs a local fallback when AgentGuard is unavailable, returns an invalid response, denies a request, or requires human approval.

## Guarded flow

1. The application constructs a typed `ToolRequest` with a registered tool ID, operation, requested environment, JSON arguments, and a stable idempotency key.
2. `AgentGuardClient.evaluate` authenticates with the agent credential and submits the request to `/api/v1/tool-requests/evaluate`.
3. A denial returns a `denied` result without calling `/api/v1/executions`.
4. A decision requiring approval returns `approval_required`. A human approves it in the existing dashboard; the agent credential cannot approve its own action.
5. An allow decision is submitted to `/api/v1/executions` with exactly the original arguments.
6. The backend revalidates the decision, permission, policy versions, detector versions, reliability state, schema, argument hash, and approval before invoking the registered adapter.

The convenience method `guarded_execute` performs steps 2 through 5. To continue a human-approved decision, call `execute(decision_id=..., arguments=...)` with the original arguments. The backend remains the authority and rejects pending, rejected, expired, or stale decisions.

## Client example

```python
from uuid import UUID

from agentguard_sdk import AgentGuardClient, ToolRequest

request = ToolRequest(
    tool_id=UUID("00000000-0000-0000-0000-000000000000"),
    operation="refund",
    environment="production",
    arguments={"order_id": "ORD-123", "amount": 100},
    idempotency_key="refund-ORD-123-attempt-1",
)

async with AgentGuardClient(
    base_url="http://127.0.0.1:8000",
    agent_token=agent_token,
) as client:
    result = await client.guarded_execute(request)
```

Remote API URLs require HTTPS by default. Plain HTTP is accepted automatically only for `localhost`, `127.0.0.1`, and `::1`. The HTTP client ignores environment proxies, refuses redirects, uses bounded timeouts, and does not retry side-effecting execution requests automatically.

## Ollama example on Windows

Create an agent and tool in the dashboard, grant the required operation, and create an agent credential. The credential is displayed once. In PowerShell, keep it only in the current process:

```powershell
$env:AGENTGUARD_AGENT_TOKEN = "<agent-credential>"
$env:AGENTGUARD_TOOL_ID = "00000000-0000-0000-0000-000000000000"

uv run python examples/ollama_guarded_agent.py `
  "Refund order ORD-123 for amount 100" `
  --idempotency-key "refund-ORD-123-attempt-1"
```

The local model proposes the operation and arguments. It cannot authorize or directly execute the tool. The example prints only the reason code or sanitized execution summary and never prints the agent credential or raw model response.

Clear the process credential when finished:

```powershell
Remove-Item Env:AGENTGUARD_AGENT_TOKEN
```

Persist the idempotency key before the first request and reuse it only for the same logical action and arguments. AgentGuard returns the prior decision for a safe retry and rejects reuse with changed request data.
