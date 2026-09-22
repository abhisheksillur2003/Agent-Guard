import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select

from backend.app.core.security import hash_password
from backend.app.models import (
    Agent,
    AgentCredential,
    Organization,
    RiskTier,
    User,
    UserRole,
    UserStatus,
)
from backend.app.services.permissions import check_permission
from backend.tests.conftest import ApiContext


async def create_user(
    context: ApiContext,
    *,
    email: str,
    role: UserRole,
    organization: Organization | None = None,
) -> tuple[User, dict[str, str]]:
    user = User(
        organization_id=(organization or context.organization).id,
        email=email,
        password_hash=hash_password("CorrectHorseBattery1!"),
        role=role,
        status=UserStatus.ACTIVE,
    )
    context.session.add(user)
    await context.session.commit()
    await context.session.refresh(user)
    response = await context.client.post(
        "/api/v1/auth/token",
        data={"username": email, "password": "CorrectHorseBattery1!"},
    )
    assert response.status_code == 200
    return user, {"Authorization": f"Bearer {response.json()['access_token']}"}


async def create_agent_and_tool(context: ApiContext) -> tuple[dict[str, object], dict[str, object]]:
    agent_response = await context.client.post(
        "/api/v1/agents",
        headers=context.admin_headers,
        json={
            "name": "support-agent",
            "description": "Handles support lookups",
            "risk_tier": "medium",
            "allowed_environments": ["local", "production"],
        },
    )
    assert agent_response.status_code == 201
    tool_response = await context.client.post(
        "/api/v1/tools",
        headers=context.admin_headers,
        json={
            "name": "search-orders",
            "description": "Read-only order lookup",
            "input_schema": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {"order_id": {"type": "string"}},
                "required": ["order_id"],
                "additionalProperties": False,
            },
            "risk_class": "low",
            "capability_flags": ["read_only"],
        },
    )
    assert tool_response.status_code == 201
    return agent_response.json(), tool_response.json()


async def test_user_login_and_current_identity(api_context: ApiContext) -> None:
    response = await api_context.client.get("/api/v1/auth/me", headers=api_context.admin_headers)
    assert response.status_code == 200
    assert response.json()["email"] == "admin@example.com"
    assert response.json()["role"] == "admin"

    invalid = await api_context.client.post(
        "/api/v1/auth/token",
        data={"username": "admin@example.com", "password": "wrong-password"},
    )
    assert invalid.status_code == 401
    assert invalid.json()["error"]["code"] == "AUTHENTICATION_FAILED"


async def test_administrator_manages_users_without_exposing_passwords(
    api_context: ApiContext,
) -> None:
    created = await api_context.client.post(
        "/api/v1/users",
        headers=api_context.admin_headers,
        json={
            "email": "managed-developer@example.com",
            "password": "ManagedDeveloper1!",
            "role": "developer",
        },
    )
    assert created.status_code == 201
    assert created.json()["role"] == "developer"
    assert "password" not in json.dumps(created.json()).lower()

    login = await api_context.client.post(
        "/api/v1/auth/token",
        data={
            "username": "managed-developer@example.com",
            "password": "ManagedDeveloper1!",
        },
    )
    assert login.status_code == 200
    developer_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    forbidden = await api_context.client.post(
        "/api/v1/users",
        headers=developer_headers,
        json={
            "email": "another@example.com",
            "password": "AnotherPassword1!",
            "role": "read_only",
        },
    )
    assert forbidden.status_code == 403

    prevent_lockout = await api_context.client.patch(
        f"/api/v1/users/{api_context.admin.id}",
        headers=api_context.admin_headers,
        json={"status": "disabled"},
    )
    assert prevent_lockout.status_code == 422

    users = await api_context.client.get("/api/v1/users", headers=api_context.admin_headers)
    assert users.status_code == 200
    assert {item["email"] for item in users.json()} == {
        "admin@example.com",
        "managed-developer@example.com",
    }


async def test_agent_credentials_rotate_and_respect_suspension(api_context: ApiContext) -> None:
    agent, _tool = await create_agent_and_tool(api_context)
    agent_id = agent["id"]
    credential_response = await api_context.client.post(
        f"/api/v1/agents/{agent_id}/credentials",
        headers=api_context.admin_headers,
        json={},
    )
    assert credential_response.status_code == 201
    first_key = credential_response.json()["credential"]
    assert first_key.startswith("agk_")

    identity = await api_context.client.get(
        "/api/v1/auth/agent/me",
        headers={"Authorization": f"Bearer {first_key}"},
    )
    assert identity.status_code == 200
    assert identity.json()["id"] == agent_id

    suspended = await api_context.client.post(
        f"/api/v1/agents/{agent_id}/suspend", headers=api_context.admin_headers
    )
    assert suspended.status_code == 200
    denied = await api_context.client.get(
        "/api/v1/auth/agent/me",
        headers={"Authorization": f"Bearer {first_key}"},
    )
    assert denied.status_code == 401

    await api_context.client.post(
        f"/api/v1/agents/{agent_id}/activate", headers=api_context.admin_headers
    )
    rotated = await api_context.client.post(
        f"/api/v1/agents/{agent_id}/credentials/rotate",
        headers=api_context.admin_headers,
        json={},
    )
    assert rotated.status_code == 200
    second_key = rotated.json()["credential"]
    assert second_key != first_key
    assert (
        await api_context.client.get(
            "/api/v1/auth/agent/me",
            headers={"Authorization": f"Bearer {first_key}"},
        )
    ).status_code == 401
    assert (
        await api_context.client.get(
            "/api/v1/auth/agent/me",
            headers={"Authorization": f"Bearer {second_key}"},
        )
    ).status_code == 200

    second_prefix = second_key.split("_", maxsplit=2)[1]
    active_credential = await api_context.session.scalar(
        select(AgentCredential).where(AgentCredential.key_prefix == second_prefix)
    )
    assert active_credential is not None
    active_credential.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await api_context.session.commit()
    assert (
        await api_context.client.get(
            "/api/v1/auth/agent/me",
            headers={"Authorization": f"Bearer {second_key}"},
        )
    ).status_code == 401


async def test_developer_can_register_but_cannot_grant_permissions(
    api_context: ApiContext,
) -> None:
    _developer, developer_headers = await create_user(
        api_context, email="developer@example.com", role=UserRole.DEVELOPER
    )
    agent_response = await api_context.client.post(
        "/api/v1/agents",
        headers=developer_headers,
        json={"name": "developer-agent", "allowed_environments": ["local"]},
    )
    assert agent_response.status_code == 201
    tool_response = await api_context.client.post(
        "/api/v1/tools",
        headers=developer_headers,
        json={
            "name": "read-tool",
            "input_schema": {"type": "object"},
            "risk_class": "low",
            "capability_flags": ["read_only"],
        },
    )
    assert tool_response.status_code == 201
    permission_response = await api_context.client.put(
        f"/api/v1/agents/{agent_response.json()['id']}/permissions/{tool_response.json()['id']}",
        headers=developer_headers,
        json={"operations": ["read"]},
    )
    assert permission_response.status_code == 403


async def test_tool_schema_validation_and_protected_updates(api_context: ApiContext) -> None:
    invalid = await api_context.client.post(
        "/api/v1/tools",
        headers=api_context.admin_headers,
        json={
            "name": "invalid-tool",
            "input_schema": {"type": "not-a-json-schema-type"},
            "risk_class": "low",
        },
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "VALIDATION_FAILED"

    _developer, developer_headers = await create_user(
        api_context, email="tool-developer@example.com", role=UserRole.DEVELOPER
    )
    _agent, tool = await create_agent_and_tool(api_context)
    response = await api_context.client.patch(
        f"/api/v1/tools/{tool['id']}",
        headers=developer_headers,
        json={"risk_class": "critical"},
    )
    assert response.status_code == 403


async def test_permissions_deny_by_default_and_match_scope(api_context: ApiContext) -> None:
    agent_data, tool_data = await create_agent_and_tool(api_context)
    agent_id = UUID(str(agent_data["id"]))
    tool_id = UUID(str(tool_data["id"]))
    decision = await check_permission(
        api_context.session,
        organization_id=api_context.organization.id,
        agent_id=agent_id,
        tool_id=tool_id,
        operation="read",
        environment="local",
    )
    assert decision.allowed is False
    assert decision.reason_code == "PERMISSION_DENIED"

    granted = await api_context.client.put(
        f"/api/v1/agents/{agent_id}/permissions/{tool_id}",
        headers=api_context.admin_headers,
        json={"operations": ["read"], "constraints": {"max_results": 25}},
    )
    assert granted.status_code == 200
    decision = await check_permission(
        api_context.session,
        organization_id=api_context.organization.id,
        agent_id=agent_id,
        tool_id=tool_id,
        operation="read",
        environment="local",
    )
    assert decision.allowed is True
    assert decision.constraints == {"max_results": 25}

    wrong_operation = await check_permission(
        api_context.session,
        organization_id=api_context.organization.id,
        agent_id=agent_id,
        tool_id=tool_id,
        operation="delete",
        environment="local",
    )
    assert wrong_operation.allowed is False


async def test_cross_organization_resources_are_hidden(api_context: ApiContext) -> None:
    other_organization = Organization(name="Other", slug="other")
    api_context.session.add(other_organization)
    await api_context.session.flush()
    other_agent = Agent(
        organization_id=other_organization.id,
        name="other-agent",
        risk_tier=RiskTier.LOW,
        allowed_environments=["local"],
    )
    api_context.session.add(other_agent)
    await api_context.session.commit()

    response = await api_context.client.get(
        f"/api/v1/agents/{other_agent.id}", headers=api_context.admin_headers
    )
    assert response.status_code == 404


async def test_credential_secret_never_enters_audit_output(api_context: ApiContext) -> None:
    agent, _tool = await create_agent_and_tool(api_context)
    response = await api_context.client.post(
        f"/api/v1/agents/{agent['id']}/credentials",
        headers=api_context.admin_headers,
        json={},
    )
    credential = response.json()["credential"]
    audit_response = await api_context.client.get(
        "/api/v1/audit", headers=api_context.admin_headers
    )
    assert audit_response.status_code == 200
    assert credential not in json.dumps(audit_response.json())

    stored_agent = await api_context.session.scalar(
        select(Agent).where(Agent.id == UUID(str(agent["id"])))
    )
    assert stored_agent is not None
