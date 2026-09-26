from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import ValidationError as PydanticValidationError

from agentguard_sdk import (
    AgentGuardAPIError,
    AgentGuardClient,
    AgentGuardConfigurationError,
    AgentGuardProtocolError,
    AgentGuardUnavailableError,
    DecisionOutcome,
    GuardedResultStatus,
    ToolRequest,
)
from backend.app.main import app
from backend.tests.conftest import ApiContext
from backend.tests.test_phase3_api import create_policy, provision_gateway


def tool_request(*, tool_id: UUID | None = None) -> ToolRequest:
    return ToolRequest(
        tool_id=tool_id or uuid4(),
        operation=" Refund ",
        environment=" Production ",
        arguments={"order_id": "ORD-123", "amount": 100},
        idempotency_key="phase12-sdk-request-001",
    )


def decision_payload(request: ToolRequest, outcome: str = "allow") -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    return {
        "id": str(uuid4()),
        "organization_id": str(uuid4()),
        "agent_id": str(uuid4()),
        "requested_tool_id": str(request.tool_id),
        "operation": request.operation,
        "environment": request.environment,
        "idempotency_key": request.idempotency_key,
        "request_id": "request-phase12",
        "outcome": outcome,
        "reason_code": {
            "allow": "DEFAULT_ALLOW",
            "deny": "POLICY_DENIED",
            "require_approval": "APPROVAL_REQUIRED",
        }[outcome],
        "permission_id": str(uuid4()),
        "matched_policy_versions": [],
        "evidence_json": {},
        "created_at": now,
    }


def execution_payload(decision: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    return {
        "id": str(uuid4()),
        "organization_id": decision["organization_id"],
        "decision_id": decision["id"],
        "approval_id": None,
        "agent_id": decision["agent_id"],
        "tool_id": decision["requested_tool_id"],
        "operation": decision["operation"],
        "environment": decision["environment"],
        "status": "succeeded",
        "adapter_name": "safe_echo",
        "adapter_version": "1",
        "result_summary": {"accepted": True},
        "error_code": None,
        "attempt_count": 1,
        "max_attempts": 1,
        "started_at": now,
        "completed_at": now,
        "created_at": now,
    }


def mock_transport(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def test_sdk_rejects_insecure_remote_urls_and_invalid_arguments() -> None:
    with pytest.raises(AgentGuardConfigurationError, match="must use HTTPS"):
        AgentGuardClient(
            base_url="http://agentguard.example.com",
            agent_token="agk_example-credential",
        )
    with pytest.raises(AgentGuardConfigurationError, match="no credentials"):
        AgentGuardClient(
            base_url="https://user:password@agentguard.example.com",
            agent_token="agk_example-credential",
        )
    with pytest.raises(PydanticValidationError, match="finite JSON"):
        ToolRequest(
            tool_id=uuid4(),
            operation="refund",
            environment="production",
            arguments={"amount": float("nan")},
            idempotency_key="phase12-invalid-json",
        )


async def test_guarded_execute_calls_adapter_only_after_allow() -> None:
    request = tool_request()
    decision = decision_payload(request)
    execution = execution_payload(decision)
    captured: list[httpx.Request] = []

    def handler(http_request: httpx.Request) -> httpx.Response:
        captured.append(http_request)
        if http_request.url.path.endswith("/tool-requests/evaluate"):
            return httpx.Response(200, json=decision)
        return httpx.Response(200, json=execution)

    async with AgentGuardClient(
        base_url="https://agentguard.example.com",
        agent_token="agk_example-credential",
        transport=mock_transport(handler),
    ) as client:
        result = await client.guarded_execute(request)

    assert result.status == GuardedResultStatus.EXECUTED
    assert result.execution is not None
    assert result.execution.status == "succeeded"
    assert [item.url.path for item in captured] == [
        "/api/v1/tool-requests/evaluate",
        "/api/v1/executions",
    ]
    assert all(
        item.headers["authorization"] == "Bearer agk_example-credential" for item in captured
    )
    assert json.loads(captured[0].content)["idempotency_key"] == request.idempotency_key
    assert request.operation == "refund"
    assert request.environment == "production"


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        ("deny", GuardedResultStatus.DENIED),
        ("require_approval", GuardedResultStatus.APPROVAL_REQUIRED),
    ],
)
async def test_guarded_execute_never_executes_blocked_decisions(
    outcome: str,
    expected: GuardedResultStatus,
) -> None:
    request = tool_request()
    calls = 0

    def handler(_http_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=decision_payload(request, outcome))

    async with AgentGuardClient(
        base_url="https://agentguard.example.com/api/v1",
        agent_token="agk_example-credential",
        transport=mock_transport(handler),
    ) as client:
        result = await client.guarded_execute(request)

    assert result.status == expected
    assert result.execution is None
    assert calls == 1


async def test_sdk_fails_closed_on_network_and_protocol_errors() -> None:
    request = tool_request()

    def unavailable(http_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection failed", request=http_request)

    async with AgentGuardClient(
        base_url="https://agentguard.example.com",
        agent_token="agk_example-credential",
        transport=mock_transport(unavailable),
    ) as client:
        with pytest.raises(AgentGuardUnavailableError, match="was not authorized"):
            await client.guarded_execute(request)

    async with AgentGuardClient(
        base_url="https://agentguard.example.com",
        agent_token="agk_example-credential",
        transport=mock_transport(lambda _request: httpx.Response(200, json={})),
    ) as client:
        with pytest.raises(AgentGuardProtocolError, match="tool action was stopped"):
            await client.guarded_execute(request)


async def test_sdk_preserves_bounded_api_error_details() -> None:
    def rejected(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={"error": {"code": "AUTHORIZATION_FAILED", "message": "Permission denied"}},
            headers={"x-request-id": "request-403"},
        )

    async with AgentGuardClient(
        base_url="https://agentguard.example.com",
        agent_token="agk_example-credential",
        transport=mock_transport(rejected),
    ) as client:
        with pytest.raises(AgentGuardAPIError) as raised:
            await client.evaluate(tool_request())

    assert raised.value.status_code == 403
    assert raised.value.code == "AUTHORIZATION_FAILED"
    assert raised.value.request_id == "request-403"
    assert "agk_example-credential" not in str(raised.value)


async def test_sdk_executes_through_real_agentguard_api(api_context: ApiContext) -> None:
    gateway = await provision_gateway(api_context, suffix="phase12-sdk")
    credential = gateway.agent_headers["Authorization"].removeprefix("Bearer ")
    request = ToolRequest(
        tool_id=gateway.tool_id,
        operation="refund",
        environment="production",
        arguments={"order_id": "ORD-123", "amount": 100, "region": "US"},
        idempotency_key="phase12-real-api-001",
    )

    async with AgentGuardClient(
        base_url="https://test",
        agent_token=credential,
        transport=httpx.ASGITransport(app=app),
    ) as client:
        result = await client.guarded_execute(request)

    assert result.decision.outcome == DecisionOutcome.ALLOW
    assert result.status == GuardedResultStatus.EXECUTED
    assert result.execution is not None
    assert result.execution.adapter_name == "safe_echo"
    assert result.execution.status == "succeeded"


async def test_sdk_continues_only_after_human_approval(api_context: ApiContext) -> None:
    gateway = await provision_gateway(api_context, suffix="phase12-approval")
    await create_policy(
        api_context,
        gateway,
        name="Phase 12 approval",
        effect="require_approval",
        reason_code="HUMAN_REVIEW_REQUIRED",
        conditions=[],
    )
    credential = gateway.agent_headers["Authorization"].removeprefix("Bearer ")
    request = ToolRequest(
        tool_id=gateway.tool_id,
        operation="refund",
        environment="production",
        arguments={"order_id": "ORD-456", "amount": 750, "region": "US"},
        idempotency_key="phase12-approval-001",
    )

    async with AgentGuardClient(
        base_url="https://test",
        agent_token=credential,
        transport=httpx.ASGITransport(app=app),
    ) as client:
        stopped = await client.guarded_execute(request)
        assert stopped.status == GuardedResultStatus.APPROVAL_REQUIRED
        assert stopped.execution is None

        approvals = await api_context.client.get(
            "/api/v1/approvals",
            params={"decision_id": str(stopped.decision.id)},
            headers=api_context.admin_headers,
        )
        assert approvals.status_code == 200
        approval_id = approvals.json()[0]["id"]
        approved = await api_context.client.post(
            f"/api/v1/approvals/{approval_id}/approve",
            json={"reason": "Reviewed for the Phase 12 SDK test"},
            headers=api_context.admin_headers,
        )
        assert approved.status_code == 200

        execution = await client.execute(
            decision_id=stopped.decision.id,
            arguments=request.arguments,
        )

    assert execution.status == "succeeded"
    assert execution.approval_id == UUID(approval_id)
