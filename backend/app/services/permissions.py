from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.errors import NotFoundError
from backend.app.models import (
    ActorType,
    Agent,
    AgentPermission,
    AgentStatus,
    Tool,
    ToolStatus,
)
from backend.app.schemas.permissions import PermissionDecision, PermissionUpsert
from backend.app.services.agents import get_agent
from backend.app.services.audit import record_audit
from backend.app.services.tools import get_tool


async def list_permissions(
    session: AsyncSession, organization_id: UUID, agent_id: UUID
) -> list[AgentPermission]:
    await get_agent(session, organization_id, agent_id)
    result = await session.scalars(
        select(AgentPermission)
        .where(AgentPermission.agent_id == agent_id)
        .order_by(AgentPermission.created_at.desc())
    )
    return list(result.all())


async def upsert_permission(
    session: AsyncSession,
    *,
    organization_id: UUID,
    agent_id: UUID,
    tool_id: UUID,
    actor_id: UUID,
    data: PermissionUpsert,
    request_id: str | None,
) -> AgentPermission:
    await get_agent(session, organization_id, agent_id)
    await get_tool(session, organization_id, tool_id)
    permission = await session.scalar(
        select(AgentPermission).where(
            AgentPermission.agent_id == agent_id,
            AgentPermission.tool_id == tool_id,
        )
    )
    before = None
    if permission is None:
        permission = AgentPermission(
            agent_id=agent_id,
            tool_id=tool_id,
            created_by=actor_id,
            operations=data.operations,
            constraints_json=data.constraints,
        )
        session.add(permission)
    else:
        before = {
            "operations": permission.operations,
            "constraints": permission.constraints_json,
        }
        permission.operations = data.operations
        permission.constraints_json = data.constraints
        permission.created_by = actor_id
    await session.flush()
    record_audit(
        session,
        organization_id=organization_id,
        actor_type=ActorType.USER,
        actor_id=actor_id,
        action="permission.upsert",
        target_type="agent_permission",
        target_id=permission.id,
        before=before,
        after={"agent_id": agent_id, "tool_id": tool_id, "operations": data.operations},
        request_id=request_id,
    )
    await session.commit()
    await session.refresh(permission)
    return permission


async def remove_permission(
    session: AsyncSession,
    *,
    organization_id: UUID,
    agent_id: UUID,
    tool_id: UUID,
    actor_id: UUID,
    request_id: str | None,
) -> None:
    await get_agent(session, organization_id, agent_id)
    await get_tool(session, organization_id, tool_id)
    permission = await session.scalar(
        select(AgentPermission).where(
            AgentPermission.agent_id == agent_id,
            AgentPermission.tool_id == tool_id,
        )
    )
    if permission is None:
        raise NotFoundError("Permission")
    snapshot = {
        "agent_id": agent_id,
        "tool_id": tool_id,
        "operations": permission.operations,
    }
    permission_id = permission.id
    await session.execute(delete(AgentPermission).where(AgentPermission.id == permission_id))
    record_audit(
        session,
        organization_id=organization_id,
        actor_type=ActorType.USER,
        actor_id=actor_id,
        action="permission.delete",
        target_type="agent_permission",
        target_id=permission_id,
        before=snapshot,
        request_id=request_id,
    )
    await session.commit()


async def check_permission(
    session: AsyncSession,
    *,
    organization_id: UUID,
    agent_id: UUID,
    tool_id: UUID,
    operation: str,
    environment: str,
) -> PermissionDecision:
    agent = await session.scalar(
        select(Agent).where(
            Agent.id == agent_id,
            Agent.organization_id == organization_id,
        )
    )
    tool = await session.scalar(
        select(Tool).where(
            Tool.id == tool_id,
            Tool.organization_id == organization_id,
        )
    )
    if agent is None or tool is None:
        return PermissionDecision(allowed=False, reason_code="PERMISSION_DENIED")
    if agent.status != AgentStatus.ACTIVE or tool.status != ToolStatus.ACTIVE:
        return PermissionDecision(allowed=False, reason_code="PERMISSION_DENIED")
    if environment.lower() not in agent.allowed_environments:
        return PermissionDecision(allowed=False, reason_code="PERMISSION_DENIED")
    permission = await session.scalar(
        select(AgentPermission).where(
            AgentPermission.agent_id == agent_id,
            AgentPermission.tool_id == tool_id,
        )
    )
    if permission is None or operation.lower() not in permission.operations:
        return PermissionDecision(allowed=False, reason_code="PERMISSION_DENIED")
    return PermissionDecision(
        allowed=True,
        reason_code="PERMISSION_GRANTED",
        permission_id=permission.id,
        constraints=permission.constraints_json,
    )
