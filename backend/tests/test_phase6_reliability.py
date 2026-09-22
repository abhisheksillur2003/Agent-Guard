from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from backend.app.models import Agent, ExecutionEvent, ExecutionStatus, ToolExecution
from backend.app.services.reliability_jobs import reconcile_stale_executions
from backend.app.services.tool_adapters import ADAPTERS, AdapterExecutionContext
from backend.tests.conftest import ApiContext
from backend.tests.test_phase3_api import GatewayContext, provision_gateway, tool_request


async def configure_budget(
    context: ApiContext,
    gateway: GatewayContext,
    **overrides: int,
) -> dict[str, Any]:
    response = await context.client.patch(
        f"/api/v1/agents/{gateway.agent_id}",
        headers=context.admin_headers,
        json={"budget_config": overrides},
    )
    assert response.status_code == 200
    return response.json()["budget_config"]


async def evaluate(
    context: ApiContext,
    gateway: GatewayContext,
    *,
    key: str,
    amount: int = 100,
    region: str = "US",
) -> dict[str, Any]:
    response = await context.client.post(
        "/api/v1/tool-requests/evaluate",
        headers=gateway.agent_headers,
        json=tool_request(gateway, key=key, amount=amount, region=region),
    )
    assert response.status_code == 200
    return response.json()


async def test_rate_limit_and_loop_detection_fail_closed(api_context: ApiContext) -> None:
    gateway = await provision_gateway(api_context, suffix="reliability-limits")
    limits = await configure_budget(
        api_context,
        gateway,
        max_decisions_per_minute=2,
        max_identical_requests_in_window=10,
    )
    assert limits["max_decisions_per_minute"] == 2
    assert limits["max_executions_per_day"] == 1_000

    assert (await evaluate(api_context, gateway, key="rate-limit-001", amount=100))[
        "outcome"
    ] == "allow"
    assert (await evaluate(api_context, gateway, key="rate-limit-002", amount=101))[
        "outcome"
    ] == "allow"
    limited = await evaluate(api_context, gateway, key="rate-limit-003", amount=102)
    assert limited["outcome"] == "deny"
    assert limited["reason_code"] == "RATE_LIMIT_EXCEEDED"
    assert limited["evidence_json"]["reliability"]["observed"]["decisions_last_minute"] == 2

    loop_gateway = await provision_gateway(api_context, suffix="loop-detection")
    await configure_budget(
        api_context,
        loop_gateway,
        max_decisions_per_minute=50,
        max_identical_requests_in_window=2,
        loop_detection_window_seconds=60,
    )
    assert (await evaluate(api_context, loop_gateway, key="loop-001"))["outcome"] == "allow"
    assert (await evaluate(api_context, loop_gateway, key="loop-002"))["outcome"] == "allow"
    loop = await evaluate(api_context, loop_gateway, key="loop-003")
    assert loop["outcome"] == "deny"
    assert loop["reason_code"] == "REQUEST_LOOP_DETECTED"


async def test_daily_execution_budget_and_invalid_configuration_deny(
    api_context: ApiContext,
) -> None:
    gateway = await provision_gateway(api_context, suffix="daily-budget")
    await configure_budget(
        api_context,
        gateway,
        max_executions_per_day=1,
        max_decisions_per_minute=50,
    )
    first = await evaluate(api_context, gateway, key="daily-budget-001")
    arguments = tool_request(gateway, key="ignored")["arguments"]
    executed = await api_context.client.post(
        "/api/v1/executions",
        headers=gateway.agent_headers,
        json={"decision_id": first["id"], "arguments": arguments},
    )
    assert executed.status_code == 200
    assert executed.json()["status"] == "succeeded"

    budget_denial = await evaluate(api_context, gateway, key="daily-budget-002", amount=101)
    assert budget_denial["outcome"] == "deny"
    assert budget_denial["reason_code"] == "DAILY_EXECUTION_BUDGET_EXCEEDED"

    invalid_gateway = await provision_gateway(api_context, suffix="invalid-reliability")
    stored_agent = await api_context.session.get(Agent, invalid_gateway.agent_id)
    assert stored_agent is not None
    stored_agent.budget_config = {"max_decisions_per_minute": 0}
    await api_context.session.commit()
    invalid = await evaluate(api_context, invalid_gateway, key="invalid-reliability-001")
    assert invalid["outcome"] == "deny"
    assert invalid["reason_code"] == "RELIABILITY_CONFIGURATION_INVALID"


class FailOnceAdapter:
    name = "fail_once_test"
    version = "1"
    retry_safe = True

    def __init__(self) -> None:
        self.execution_ids: list[str] = []

    async def execute(
        self,
        _arguments: dict[str, Any],
        context: AdapterExecutionContext,
    ) -> dict[str, Any]:
        self.execution_ids.append(str(context.execution_id))
        if len(self.execution_ids) == 1:
            raise RuntimeError("simulated transient failure")
        return {"recovered": True, "execution_id": str(context.execution_id)}


async def test_bounded_retry_reuses_the_execution_id(
    api_context: ApiContext,
    monkeypatch: Any,
) -> None:
    adapter = FailOnceAdapter()
    monkeypatch.setitem(ADAPTERS, (adapter.name, adapter.version), adapter)
    gateway = await provision_gateway(api_context, suffix="bounded-retry")
    await configure_budget(
        api_context,
        gateway,
        max_execution_attempts=2,
        retry_backoff_seconds=0,
    )
    configured = await api_context.client.patch(
        f"/api/v1/tools/{gateway.tool_id}",
        headers=api_context.admin_headers,
        json={"adapter_name": adapter.name, "adapter_version": adapter.version},
    )
    assert configured.status_code == 200

    decision = await evaluate(api_context, gateway, key="bounded-retry-001")
    arguments = tool_request(gateway, key="ignored")["arguments"]
    first = await api_context.client.post(
        "/api/v1/executions",
        headers=gateway.agent_headers,
        json={"decision_id": decision["id"], "arguments": arguments},
    )
    assert first.status_code == 200
    assert first.json()["status"] == "failed"
    assert first.json()["attempt_count"] == 1
    assert first.json()["max_attempts"] == 2

    retried = await api_context.client.post(
        f"/api/v1/executions/{first.json()['id']}/retry",
        headers=gateway.agent_headers,
        json={"arguments": arguments},
    )
    assert retried.status_code == 200
    assert retried.json()["id"] == first.json()["id"]
    assert retried.json()["status"] == "succeeded"
    assert retried.json()["attempt_count"] == 2
    assert adapter.execution_ids == [first.json()["id"], first.json()["id"]]

    events = await api_context.client.get(
        f"/api/v1/executions/{first.json()['id']}/events",
        headers=api_context.admin_headers,
    )
    assert [item["status"] for item in events.json()] == [
        "authorized",
        "running",
        "failed",
        "running",
        "succeeded",
    ]


async def test_reconciliation_marks_lost_running_execution(api_context: ApiContext) -> None:
    gateway = await provision_gateway(api_context, suffix="reconciliation")
    decision = await evaluate(api_context, gateway, key="reconciliation-001")
    arguments = tool_request(gateway, key="ignored")["arguments"]
    response = await api_context.client.post(
        "/api/v1/executions",
        headers=gateway.agent_headers,
        json={"decision_id": decision["id"], "arguments": arguments},
    )
    execution = await api_context.session.get(ToolExecution, response.json()["id"])
    assert execution is not None
    execution.status = ExecutionStatus.RUNNING
    execution.started_at = datetime.now(UTC) - timedelta(minutes=10)
    terminal = await api_context.session.scalar(
        select(ExecutionEvent).where(
            ExecutionEvent.execution_id == execution.id,
            ExecutionEvent.sequence == 3,
        )
    )
    assert terminal is not None
    await api_context.session.delete(terminal)
    await api_context.session.commit()

    assert await reconcile_stale_executions(api_context.session, 300) == 1
    await api_context.session.refresh(execution)
    assert execution.status == ExecutionStatus.FAILED
    assert execution.error_code == "EXECUTION_WORKER_LOST"
