import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select

from backend.app.models import PolicyDecision, PolicyVersion
from backend.app.schemas.policies import UtcHourOutsideCondition
from backend.app.services.policy_engine import condition_matches
from backend.tests.conftest import ApiContext


@dataclass
class GatewayContext:
    agent_id: UUID
    tool_id: UUID
    agent_headers: dict[str, str]


async def provision_gateway(
    context: ApiContext,
    *,
    suffix: str,
    grant_permission: bool = True,
) -> GatewayContext:
    agent_response = await context.client.post(
        "/api/v1/agents",
        headers=context.admin_headers,
        json={
            "name": f"gateway-agent-{suffix}",
            "allowed_environments": ["local", "production"],
        },
    )
    assert agent_response.status_code == 201
    agent_id = UUID(agent_response.json()["id"])
    tool_response = await context.client.post(
        "/api/v1/tools",
        headers=context.admin_headers,
        json={
            "name": f"refund-tool-{suffix}",
            "description": "Processes a refund after AgentGuard authorization",
            "input_schema": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "amount": {"type": "number", "minimum": 0},
                    "region": {"type": "string"},
                },
                "required": ["order_id", "amount"],
                "additionalProperties": False,
            },
            "risk_class": "high",
            "capability_flags": ["financial", "write"],
        },
    )
    assert tool_response.status_code == 201
    tool_id = UUID(tool_response.json()["id"])
    if grant_permission:
        permission = await context.client.put(
            f"/api/v1/agents/{agent_id}/permissions/{tool_id}",
            headers=context.admin_headers,
            json={"operations": ["refund"]},
        )
        assert permission.status_code == 200
    credential_response = await context.client.post(
        f"/api/v1/agents/{agent_id}/credentials",
        headers=context.admin_headers,
        json={},
    )
    assert credential_response.status_code == 201
    credential = credential_response.json()["credential"]
    return GatewayContext(
        agent_id=agent_id,
        tool_id=tool_id,
        agent_headers={"Authorization": f"Bearer {credential}"},
    )


def tool_request(
    gateway: GatewayContext,
    *,
    key: str,
    amount: Any = 100,
    region: str = "US",
) -> dict[str, Any]:
    return {
        "tool_id": str(gateway.tool_id),
        "operation": "refund",
        "environment": "production",
        "arguments": {"order_id": "ORD-123", "amount": amount, "region": region},
        "idempotency_key": key,
    }


async def create_policy(
    context: ApiContext,
    gateway: GatewayContext,
    *,
    name: str,
    effect: str,
    reason_code: str,
    conditions: list[dict[str, Any]],
    priority: int = 100,
) -> dict[str, Any]:
    response = await context.client.post(
        "/api/v1/policies",
        headers=context.admin_headers,
        json={
            "name": name,
            "priority": priority,
            "document": {
                "scope": {
                    "agent_ids": [str(gateway.agent_id)],
                    "tool_ids": [str(gateway.tool_id)],
                    "environments": ["production"],
                    "operations": ["refund"],
                },
                "effect": effect,
                "reason_code": reason_code,
                "conditions": conditions,
            },
        },
    )
    assert response.status_code == 201
    return response.json()


async def test_missing_permission_is_durably_denied(api_context: ApiContext) -> None:
    gateway = await provision_gateway(api_context, suffix="default-deny", grant_permission=False)
    response = await api_context.client.post(
        "/api/v1/tool-requests/evaluate",
        headers={**gateway.agent_headers, "x-request-id": "phase3-default-deny"},
        json=tool_request(gateway, key="default-deny-001"),
    )
    assert response.status_code == 200
    assert response.json()["outcome"] == "deny"
    assert response.json()["reason_code"] == "PERMISSION_DENIED"
    assert response.json()["request_id"] == "phase3-default-deny"

    decision_id = UUID(response.json()["id"])
    stored = await api_context.session.get(PolicyDecision, decision_id)
    assert stored is not None
    assert stored.outcome == "deny"
    assert not hasattr(stored, "arguments")


async def test_allow_decision_is_idempotent_and_payload_bound(api_context: ApiContext) -> None:
    gateway = await provision_gateway(api_context, suffix="idempotent")
    request = tool_request(gateway, key="idempotency-001")
    first = await api_context.client.post(
        "/api/v1/tool-requests/evaluate",
        headers=gateway.agent_headers,
        json=request,
    )
    assert first.status_code == 200
    assert first.json()["outcome"] == "allow"
    assert first.json()["reason_code"] == "POLICY_CHECKS_PASSED"

    retry = await api_context.client.post(
        "/api/v1/tool-requests/evaluate",
        headers=gateway.agent_headers,
        json=request,
    )
    assert retry.status_code == 200
    assert retry.json()["id"] == first.json()["id"]

    conflicting = tool_request(gateway, key="idempotency-001", amount=101)
    conflict_response = await api_context.client.post(
        "/api/v1/tool-requests/evaluate",
        headers=gateway.agent_headers,
        json=conflicting,
    )
    assert conflict_response.status_code == 409


async def test_invalid_arguments_are_denied_without_storing_payload(
    api_context: ApiContext,
) -> None:
    gateway = await provision_gateway(api_context, suffix="schema")
    secret_value = "raw-sensitive-invalid-value"
    response = await api_context.client.post(
        "/api/v1/tool-requests/evaluate",
        headers=gateway.agent_headers,
        json=tool_request(gateway, key="invalid-schema-001", amount=secret_value),
    )
    assert response.status_code == 200
    assert response.json()["outcome"] == "deny"
    assert response.json()["reason_code"] == "INPUT_SCHEMA_INVALID"
    assert secret_value not in json.dumps(response.json())

    stored = await api_context.session.get(PolicyDecision, UUID(response.json()["id"]))
    assert stored is not None
    assert secret_value not in json.dumps(stored.evidence_json)


async def test_policy_versions_are_immutable_and_status_is_enforced(
    api_context: ApiContext,
) -> None:
    gateway = await provision_gateway(api_context, suffix="versions")
    policy = await create_policy(
        api_context,
        gateway,
        name="Large refunds require approval",
        effect="require_approval",
        reason_code="REFUND_APPROVAL_REQUIRED",
        conditions=[{"type": "number_gt", "path": "amount", "value": 500}],
    )
    first = await api_context.client.post(
        "/api/v1/tool-requests/evaluate",
        headers=gateway.agent_headers,
        json=tool_request(gateway, key="version-one-001", amount=1000),
    )
    assert first.json()["outcome"] == "require_approval"
    assert first.json()["matched_policy_versions"][0]["version"] == 1

    updated_document = policy["document"]
    updated_document["conditions"][0]["value"] = 1500
    updated = await api_context.client.patch(
        f"/api/v1/policies/{policy['id']}",
        headers=api_context.admin_headers,
        json={"document": updated_document},
    )
    assert updated.status_code == 200
    assert updated.json()["current_version"] == 2
    versions = await api_context.client.get(
        f"/api/v1/policies/{policy['id']}/versions",
        headers=api_context.admin_headers,
    )
    assert [item["version"] for item in versions.json()] == [2, 1]
    assert versions.json()[1]["document"]["conditions"][0]["value"] == 500

    below_new_limit = await api_context.client.post(
        "/api/v1/tool-requests/evaluate",
        headers=gateway.agent_headers,
        json=tool_request(gateway, key="version-two-001", amount=1000),
    )
    assert below_new_limit.json()["outcome"] == "allow"

    disabled = await api_context.client.patch(
        f"/api/v1/policies/{policy['id']}",
        headers=api_context.admin_headers,
        json={"status": "disabled"},
    )
    assert disabled.status_code == 200
    while_disabled = await api_context.client.post(
        "/api/v1/tool-requests/evaluate",
        headers=gateway.agent_headers,
        json=tool_request(gateway, key="disabled-policy-001", amount=2000),
    )
    assert while_disabled.json()["outcome"] == "allow"


async def test_deny_takes_precedence_over_approval(api_context: ApiContext) -> None:
    gateway = await provision_gateway(api_context, suffix="precedence")
    await create_policy(
        api_context,
        gateway,
        name="Approval for elevated refunds",
        effect="require_approval",
        reason_code="REFUND_APPROVAL_REQUIRED",
        conditions=[{"type": "number_gt", "path": "amount", "value": 500}],
        priority=10,
    )
    await create_policy(
        api_context,
        gateway,
        name="Block prohibited region",
        effect="deny",
        reason_code="REGION_BLOCKED",
        conditions=[{"type": "value_in", "path": "region", "values": ["BLOCKED"]}],
        priority=200,
    )
    response = await api_context.client.post(
        "/api/v1/tool-requests/evaluate",
        headers=gateway.agent_headers,
        json=tool_request(
            gateway,
            key="deny-precedence-001",
            amount=1000,
            region="BLOCKED",
        ),
    )
    assert response.status_code == 200
    assert response.json()["outcome"] == "deny"
    assert response.json()["reason_code"] == "REGION_BLOCKED"
    assert len(response.json()["matched_policy_versions"]) == 2


async def test_invalid_stored_policy_fails_closed(api_context: ApiContext) -> None:
    gateway = await provision_gateway(api_context, suffix="fail-closed")
    policy = await create_policy(
        api_context,
        gateway,
        name="Policy that will be corrupted",
        effect="deny",
        reason_code="BLOCKED",
        conditions=[],
    )
    version = await api_context.session.scalar(
        select(PolicyVersion).where(PolicyVersion.policy_id == UUID(policy["id"]))
    )
    assert version is not None
    version.document_json = {"effect": "invalid"}
    await api_context.session.commit()

    response = await api_context.client.post(
        "/api/v1/tool-requests/evaluate",
        headers=gateway.agent_headers,
        json=tool_request(gateway, key="invalid-policy-001"),
    )
    assert response.status_code == 200
    assert response.json()["outcome"] == "deny"
    assert response.json()["reason_code"] == "POLICY_CONFIGURATION_INVALID"


async def test_utc_time_window_condition_handles_wrapped_windows() -> None:
    condition = UtcHourOutsideCondition(
        type="utc_hour_outside",
        start_hour=22,
        end_hour=6,
    )
    assert condition_matches(condition, {}, datetime(2026, 1, 1, 23, tzinfo=UTC)) is False
    assert condition_matches(condition, {}, datetime(2026, 1, 1, 12, tzinfo=UTC)) is True
