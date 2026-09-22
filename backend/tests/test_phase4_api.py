import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select

from backend.app.models import ApprovalRequest, ExecutionEvent, ToolExecution
from backend.app.services.tool_adapters import (
    ADAPTERS,
    AdapterExecutionContext,
    sanitize_result,
)
from backend.tests.conftest import ApiContext
from backend.tests.test_phase3_api import (
    GatewayContext,
    create_policy,
    provision_gateway,
    tool_request,
)


async def evaluate(
    context: ApiContext,
    gateway: GatewayContext,
    *,
    key: str,
    amount: Any = 1000,
) -> dict[str, Any]:
    response = await context.client.post(
        "/api/v1/tool-requests/evaluate",
        headers=gateway.agent_headers,
        json=tool_request(gateway, key=key, amount=amount),
    )
    assert response.status_code == 200
    return response.json()


async def approval_for(context: ApiContext, decision_id: str) -> dict[str, Any]:
    response = await context.client.get(
        "/api/v1/approvals",
        params={"decision_id": decision_id},
        headers=context.admin_headers,
    )
    assert response.status_code == 200
    assert len(response.json()) == 1
    return response.json()[0]


async def test_approved_request_executes_once_with_ordered_events(
    api_context: ApiContext,
) -> None:
    gateway = await provision_gateway(api_context, suffix="approved-execution")
    await create_policy(
        api_context,
        gateway,
        name="Approve large execution",
        effect="require_approval",
        reason_code="APPROVAL_REQUIRED",
        conditions=[{"type": "number_gt", "path": "amount", "value": 500}],
    )
    decision = await evaluate(
        api_context,
        gateway,
        key="approved-execution-001",
    )
    assert decision["outcome"] == "require_approval"
    approval = await approval_for(api_context, decision["id"])
    assert approval["status"] == "pending"

    approved = await api_context.client.post(
        f"/api/v1/approvals/{approval['id']}/approve",
        headers=api_context.admin_headers,
        json={"reason": "Verified order and refund amount"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"

    arguments = tool_request(gateway, key="ignored", amount=1000)["arguments"]
    executed = await api_context.client.post(
        "/api/v1/executions",
        headers=gateway.agent_headers,
        json={"decision_id": decision["id"], "arguments": arguments},
    )
    assert executed.status_code == 200
    assert executed.json()["status"] == "succeeded"
    assert executed.json()["approval_id"] == approval["id"]
    assert executed.json()["result_summary"] == {
        "accepted": True,
        "argument_fields": ["amount", "order_id", "region"],
        "argument_count": 3,
        "execution_id": executed.json()["id"],
    }
    assert "ORD-123" not in json.dumps(executed.json())

    retry = await api_context.client.post(
        "/api/v1/executions",
        headers=gateway.agent_headers,
        json={"decision_id": decision["id"], "arguments": arguments},
    )
    assert retry.status_code == 200
    assert retry.json()["id"] == executed.json()["id"]
    execution_count = await api_context.session.scalar(
        select(func.count()).select_from(ToolExecution)
    )
    assert execution_count == 1

    events = await api_context.client.get(
        f"/api/v1/executions/{executed.json()['id']}/events",
        headers=api_context.admin_headers,
    )
    assert events.status_code == 200
    assert [item["sequence"] for item in events.json()] == [1, 2, 3]
    assert [item["status"] for item in events.json()] == [
        "authorized",
        "running",
        "succeeded",
    ]


async def test_pending_rejected_and_expired_approvals_block_execution(
    api_context: ApiContext,
) -> None:
    gateway = await provision_gateway(api_context, suffix="approval-blocks")
    await create_policy(
        api_context,
        gateway,
        name="Always require approval",
        effect="require_approval",
        reason_code="APPROVAL_REQUIRED",
        conditions=[],
    )
    arguments = tool_request(gateway, key="ignored", amount=1000)["arguments"]

    pending_decision = await evaluate(api_context, gateway, key="pending-approval-001")
    blocked_pending = await api_context.client.post(
        "/api/v1/executions",
        headers=gateway.agent_headers,
        json={"decision_id": pending_decision["id"], "arguments": arguments},
    )
    assert blocked_pending.status_code == 403

    pending_approval = await approval_for(api_context, pending_decision["id"])
    rejected = await api_context.client.post(
        f"/api/v1/approvals/{pending_approval['id']}/reject",
        headers=api_context.admin_headers,
        json={"reason": "Refund evidence is insufficient"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    blocked_rejected = await api_context.client.post(
        "/api/v1/executions",
        headers=gateway.agent_headers,
        json={"decision_id": pending_decision["id"], "arguments": arguments},
    )
    assert blocked_rejected.status_code == 403

    expired_decision = await evaluate(api_context, gateway, key="expired-approval-001")
    expired_data = await approval_for(api_context, expired_decision["id"])
    stored = await api_context.session.get(ApprovalRequest, UUID(expired_data["id"]))
    assert stored is not None
    stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await api_context.session.commit()
    expired = await api_context.client.post(
        f"/api/v1/approvals/{expired_data['id']}/approve",
        headers=api_context.admin_headers,
        json={"reason": "Attempt after expiry"},
    )
    assert expired.status_code == 409
    await api_context.session.refresh(stored)
    assert stored.status == "expired"


async def test_execution_rejects_changed_arguments_and_stale_policy_configuration(
    api_context: ApiContext,
) -> None:
    gateway = await provision_gateway(api_context, suffix="execution-binding")
    decision = await evaluate(
        api_context,
        gateway,
        key="execution-binding-001",
        amount=100,
    )
    assert decision["outcome"] == "allow"
    changed_arguments = tool_request(gateway, key="ignored", amount=101)["arguments"]
    changed = await api_context.client.post(
        "/api/v1/executions",
        headers=gateway.agent_headers,
        json={"decision_id": decision["id"], "arguments": changed_arguments},
    )
    assert changed.status_code == 409

    await create_policy(
        api_context,
        gateway,
        name="New policy invalidates old authorization",
        effect="deny",
        reason_code="NEW_POLICY_REQUIRES_RECHECK",
        conditions=[],
    )
    original_arguments = tool_request(gateway, key="ignored", amount=100)["arguments"]
    stale = await api_context.client.post(
        "/api/v1/executions",
        headers=gateway.agent_headers,
        json={"decision_id": decision["id"], "arguments": original_arguments},
    )
    assert stale.status_code == 403
    assert "evaluate the request again" in stale.json()["error"]["message"]


async def test_agent_owner_cannot_approve_own_request(api_context: ApiContext) -> None:
    gateway = await provision_gateway(api_context, suffix="separation-of-duties")
    owner_update = await api_context.client.patch(
        f"/api/v1/agents/{gateway.agent_id}",
        headers=api_context.admin_headers,
        json={"owner_user_id": str(api_context.admin.id)},
    )
    assert owner_update.status_code == 200
    await create_policy(
        api_context,
        gateway,
        name="Owner separation",
        effect="require_approval",
        reason_code="INDEPENDENT_APPROVAL_REQUIRED",
        conditions=[],
    )
    decision = await evaluate(api_context, gateway, key="owner-approval-001")
    approval = await approval_for(api_context, decision["id"])
    response = await api_context.client.post(
        f"/api/v1/approvals/{approval['id']}/approve",
        headers=api_context.admin_headers,
        json={"reason": "Owner tries to approve"},
    )
    assert response.status_code == 403


class SlowTestAdapter:
    name = "slow_test"
    version = "1"

    async def execute(
        self,
        arguments: dict[str, Any],
        context: AdapterExecutionContext,
    ) -> dict[str, Any]:
        await asyncio.sleep(2)
        return {"unexpected": arguments, "execution_id": str(context.execution_id)}


async def test_adapter_timeout_is_recorded_without_retrying(
    api_context: ApiContext,
    monkeypatch: Any,
) -> None:
    monkeypatch.setitem(ADAPTERS, ("slow_test", "1"), SlowTestAdapter())
    gateway = await provision_gateway(api_context, suffix="timeout")
    configured = await api_context.client.patch(
        f"/api/v1/tools/{gateway.tool_id}",
        headers=api_context.admin_headers,
        json={
            "adapter_name": "slow_test",
            "adapter_version": "1",
            "execution_timeout_seconds": 1,
        },
    )
    assert configured.status_code == 200
    decision = await evaluate(api_context, gateway, key="timeout-execution-001", amount=100)
    arguments = tool_request(gateway, key="ignored", amount=100)["arguments"]
    response = await api_context.client.post(
        "/api/v1/executions",
        headers=gateway.agent_headers,
        json={"decision_id": decision["id"], "arguments": arguments},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "timed_out"
    assert response.json()["error_code"] == "EXECUTION_TIMEOUT"
    event_count = await api_context.session.scalar(select(func.count()).select_from(ExecutionEvent))
    assert event_count == 3


def test_result_sanitizer_redacts_and_limits_sensitive_output() -> None:
    sanitized = sanitize_result(
        {
            "access_token": "secret-token-value",
            "nested": {"password": "hidden", "message": "x" * 600},
        }
    )
    assert sanitized["access_token"] == "[REDACTED]"
    assert sanitized["nested"]["password"] == "[REDACTED]"
    assert len(sanitized["nested"]["message"]) == 500
