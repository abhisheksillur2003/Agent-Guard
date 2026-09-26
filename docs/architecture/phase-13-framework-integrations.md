# Phase 13: LangChain and CrewAI integrations

Phase 13 exposes registered AgentGuard tools through the native LangChain `StructuredTool` and CrewAI `BaseTool` interfaces. The adapters use the Phase 12 SDK and do not contain a local execution callback, so a framework cannot bypass AgentGuard when the API is unavailable or returns an invalid response.

The implementation targets `langchain-core` 1.6 and CrewAI 1.15. It follows the official [LangChain tools contract](https://docs.langchain.com/oss/python/langchain/tools) and [CrewAI custom-tool contract](https://docs.crewai.com/en/learn/create-custom-tools).

## Install optional framework dependencies

Neither framework is installed in the production API image. Install only the integration needed by the agent application:

```powershell
uv sync --extra langchain
uv sync --extra crewai
# Or install both:
uv sync --extra frameworks
```

Repository development uses `uv sync --all-groups`, which includes both frameworks for integration tests.

## Configuration and input schema

Each wrapper receives an operator-controlled configuration and a Pydantic input model matching the tool schema registered in AgentGuard:

```python
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from agentguard_sdk.integrations import FrameworkToolConfig


class RefundArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str = Field(min_length=1)
    amount: float = Field(ge=0)
    region: str = "US"


config = FrameworkToolConfig(
    name="guarded_refund",
    description="Request a refund through AgentGuard.",
    base_url="http://127.0.0.1:8000",
    agent_token=SecretStr(agent_token),
    tool_id=tool_id,
    operation="refund",
    environment="production",
    run_id=framework_run_id,
)
```

The framework run ID is hashed and never sent as evidence. Create one stable ID for each logical agent or crew run, persist it before the first tool request, and reuse it for framework retries. A different run must use a different ID. AgentGuard combines it with the framework, tool, operation, environment, and canonical arguments to create a bounded idempotency key.

## LangChain

```python
from agentguard_sdk.integrations.langchain import create_langchain_tool

guarded_refund = create_langchain_tool(
    config=config,
    args_schema=RefundArguments,
)

# Pass guarded_refund to create_agent(...), or invoke it directly.
output = await guarded_refund.ainvoke({"order_id": "ORD-123", "amount": 100, "region": "US"})
```

LangChain receives a native `StructuredTool` with synchronous and asynchronous implementations. Use `ainvoke` inside an active event loop. A synchronous invocation inside an event loop stops with an explicit integration error instead of attempting nested loop execution.

## CrewAI

```python
from agentguard_sdk.integrations.crewai import create_crewai_tool

guarded_refund = create_crewai_tool(
    config=config,
    args_schema=RefundArguments,
)

# Add guarded_refund to Agent(tools=[...]), or invoke it directly.
output = await guarded_refund.arun(
    order_id="ORD-123",
    amount=100,
    region="US",
)
```

CrewAI receives a native `BaseTool` with the supplied Pydantic argument schema and a typed `FrameworkToolOutput` result schema.

## Decisions and approval continuation

Both integrations return only bounded structured fields: status, reason code, decision ID, execution ID and status, sanitized adapter summary, and a bounded error code. A denial or approval requirement never calls `/api/v1/executions`.

For an approval requirement, retain the original arguments and decision ID. After a human approves the request in AgentGuard, the host application can continue through the same runner:

```python
output = await runner.resume_approved(
    decision_id=approval_output.decision_id,
    arguments=original_arguments,
)
```

The runner does not trust the caller's claim that approval occurred. The backend rechecks the durable approval, argument hash, decision age, permission, policies, detectors, schema, and reliability limits before executing. Pending, rejected, expired, or changed requests remain blocked.

## Windows Ollama examples

The examples use Ollama only to propose typed arguments, then invoke the native framework tool. AgentGuard remains the only execution path.

```powershell
$env:AGENTGUARD_AGENT_TOKEN = "<agent-credential>"
$env:AGENTGUARD_TOOL_ID = "00000000-0000-0000-0000-000000000000"
$env:AGENTGUARD_RUN_ID = "support-session-2026-09-27-001"

uv run python -m examples.langchain_guarded_agent `
  "Refund order ORD-123 for amount 100"

uv run python -m examples.crewai_guarded_agent `
  "Refund order ORD-123 for amount 100"
```

The example schema is the refund schema shown above. Update the Pydantic model and registered AgentGuard tool schema together for another operation. Clear the process credential after testing:

```powershell
Remove-Item Env:AGENTGUARD_AGENT_TOKEN
```

## Failure behavior

- AgentGuard denial returns `denied` without adapter execution.
- Required approval returns `approval_required` without adapter execution.
- Network, authentication, protocol, and configuration failures raise `FrameworkIntegrationError`.
- Framework retries reuse the same idempotency key only when the run ID and canonical request are unchanged.
- No wrapper accepts a direct tool callback or catches failures by executing locally.
