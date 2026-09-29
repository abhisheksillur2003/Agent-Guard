from sqlalchemy import func, select

from backend.app.core.errors import ValidationError
from backend.app.models import (
    Agent,
    AgentCredential,
    AgentPermission,
    Policy,
    SecurityDetector,
    Tool,
)
from backend.app.services.local_demo import (
    DEMO_AGENT_NAME,
    DEMO_POLICY_NAME,
    DEMO_TOOL_NAME,
    seed_local_demo,
)
from backend.tests.conftest import ApiContext


async def test_local_demo_seeds_guarded_workspace_and_is_idempotent(
    api_context: ApiContext,
) -> None:
    first = await seed_local_demo(
        api_context.session,
        admin_email=api_context.admin.email,
        environment="local",
    )

    assert first.credential is not None
    assert set(first.created) == {
        "agent",
        "tool",
        "permission",
        "policy",
        "agent_credential",
        "detector:Block secrets in local requests",
        "detector:Record PII in local requests",
        "detector:Review prompt manipulation",
    }
    credential = await api_context.session.scalar(
        select(AgentCredential).where(AgentCredential.agent_id == first.agent_id)
    )
    assert credential is not None
    assert credential.secret_hash != first.credential

    second = await seed_local_demo(
        api_context.session,
        admin_email=api_context.admin.email,
        environment="local",
    )
    assert second.created == ()
    assert second.credential is None
    assert second.agent_id == first.agent_id
    assert second.tool_id == first.tool_id

    queries = (
        select(func.count()).select_from(Agent).where(Agent.name == DEMO_AGENT_NAME),
        select(func.count()).select_from(Tool).where(Tool.name == DEMO_TOOL_NAME),
        select(func.count()).select_from(AgentPermission),
        select(func.count()).select_from(Policy).where(Policy.name == DEMO_POLICY_NAME),
        select(func.count()).select_from(SecurityDetector),
        select(func.count()).select_from(AgentCredential),
    )
    counts = [await api_context.session.scalar(query) for query in queries]
    assert counts == [1, 1, 1, 1, 3, 1]


async def test_local_demo_exercises_allow_approval_and_deny_paths(
    api_context: ApiContext,
) -> None:
    demo = await seed_local_demo(
        api_context.session,
        admin_email=api_context.admin.email,
        environment="local",
    )
    assert demo.credential is not None
    headers = {"Authorization": f"Bearer {demo.credential}"}

    allowed_arguments = {"order_id": "ORD-LOCAL-100", "amount": 100}
    allowed = await api_context.client.post(
        "/api/v1/tool-requests/evaluate",
        headers=headers,
        json={
            "tool_id": str(demo.tool_id),
            "operation": "refund",
            "environment": "local",
            "arguments": allowed_arguments,
            "idempotency_key": "local-demo-allow-001",
        },
    )
    assert allowed.status_code == 200
    assert allowed.json()["outcome"] == "allow"
    execution = await api_context.client.post(
        "/api/v1/executions",
        headers=headers,
        json={"decision_id": allowed.json()["id"], "arguments": allowed_arguments},
    )
    assert execution.status_code == 200
    assert execution.json()["status"] == "succeeded"

    approval = await api_context.client.post(
        "/api/v1/tool-requests/evaluate",
        headers=headers,
        json={
            "tool_id": str(demo.tool_id),
            "operation": "refund",
            "environment": "local",
            "arguments": {"order_id": "ORD-LOCAL-900", "amount": 900},
            "idempotency_key": "local-demo-approval-001",
        },
    )
    assert approval.status_code == 200
    assert approval.json()["outcome"] == "require_approval"
    assert approval.json()["reason_code"] == "LARGE_REFUND_REVIEW"

    synthetic_secret = "api_key=abcdefghijklmnopqrstuvwxyz123456"
    denied = await api_context.client.post(
        "/api/v1/tool-requests/evaluate",
        headers=headers,
        json={
            "tool_id": str(demo.tool_id),
            "operation": "refund",
            "environment": "local",
            "arguments": {
                "order_id": "ORD-LOCAL-SECRET",
                "amount": 10,
                "customer_message": synthetic_secret,
            },
            "idempotency_key": "local-demo-deny-001",
        },
    )
    assert denied.status_code == 200
    assert denied.json()["outcome"] == "deny"
    assert denied.json()["reason_code"] == "LOCAL_SECRET_DETECTED"
    assert synthetic_secret not in denied.text


async def test_local_demo_refuses_non_local_environments(api_context: ApiContext) -> None:
    try:
        await seed_local_demo(
            api_context.session,
            admin_email=api_context.admin.email,
            environment="production",
        )
    except ValidationError as exc:
        assert "local environment" in exc.message
    else:
        raise AssertionError("Production demo bootstrap must fail closed")

    count = await api_context.session.scalar(select(func.count()).select_from(Agent))
    assert count == 0
