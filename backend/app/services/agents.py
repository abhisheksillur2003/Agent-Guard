from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.errors import ConflictError, NotFoundError, ValidationError
from backend.app.core.security import generate_agent_key
from backend.app.models import (
    ActorType,
    Agent,
    AgentCredential,
    AgentStatus,
    CredentialStatus,
    User,
)
from backend.app.schemas.agents import AgentCreate, AgentUpdate
from backend.app.services.audit import record_audit


def agent_snapshot(agent: Agent) -> dict[str, Any]:
    return {
        "name": agent.name,
        "description": agent.description,
        "owner_user_id": agent.owner_user_id,
        "status": agent.status,
        "risk_tier": agent.risk_tier,
        "allowed_environments": agent.allowed_environments,
        "budget_config": agent.budget_config,
    }


async def get_agent(session: AsyncSession, organization_id: UUID, agent_id: UUID) -> Agent:
    agent = await session.scalar(
        select(Agent).where(
            Agent.id == agent_id,
            Agent.organization_id == organization_id,
        )
    )
    if agent is None:
        raise NotFoundError("Agent")
    return agent


async def list_agents(session: AsyncSession, organization_id: UUID) -> list[Agent]:
    result = await session.scalars(
        select(Agent)
        .where(Agent.organization_id == organization_id)
        .order_by(Agent.created_at.desc())
    )
    return list(result.all())


async def _validate_owner(
    session: AsyncSession, organization_id: UUID, owner_user_id: UUID | None
) -> None:
    if owner_user_id is None:
        return
    owner = await session.scalar(
        select(User.id).where(
            User.id == owner_user_id,
            User.organization_id == organization_id,
        )
    )
    if owner is None:
        raise ValidationError("Agent owner must belong to the same organization")


async def create_agent(
    session: AsyncSession,
    *,
    organization_id: UUID,
    actor_id: UUID,
    data: AgentCreate,
    request_id: str | None,
) -> Agent:
    duplicate = await session.scalar(
        select(Agent.id).where(
            Agent.organization_id == organization_id,
            Agent.name == data.name,
        )
    )
    if duplicate is not None:
        raise ConflictError("An agent with this name already exists")
    await _validate_owner(session, organization_id, data.owner_user_id)

    agent = Agent(organization_id=organization_id, **data.model_dump())
    session.add(agent)
    await session.flush()
    record_audit(
        session,
        organization_id=organization_id,
        actor_type=ActorType.USER,
        actor_id=actor_id,
        action="agent.create",
        target_type="agent",
        target_id=agent.id,
        after=agent_snapshot(agent),
        request_id=request_id,
    )
    await session.commit()
    await session.refresh(agent)
    return agent


async def update_agent(
    session: AsyncSession,
    *,
    organization_id: UUID,
    agent_id: UUID,
    actor_id: UUID,
    data: AgentUpdate,
    request_id: str | None,
) -> Agent:
    agent = await get_agent(session, organization_id, agent_id)
    before = agent_snapshot(agent)
    changes = data.model_dump(exclude_unset=True)
    if "owner_user_id" in changes:
        await _validate_owner(session, organization_id, changes["owner_user_id"])
    if "name" in changes and changes["name"] != agent.name:
        duplicate = await session.scalar(
            select(Agent.id).where(
                Agent.organization_id == organization_id,
                Agent.name == changes["name"],
                Agent.id != agent.id,
            )
        )
        if duplicate is not None:
            raise ConflictError("An agent with this name already exists")
    for field, value in changes.items():
        setattr(agent, field, value)
    record_audit(
        session,
        organization_id=organization_id,
        actor_type=ActorType.USER,
        actor_id=actor_id,
        action="agent.update",
        target_type="agent",
        target_id=agent.id,
        before=before,
        after=agent_snapshot(agent),
        request_id=request_id,
    )
    await session.commit()
    await session.refresh(agent)
    return agent


async def set_agent_status(
    session: AsyncSession,
    *,
    organization_id: UUID,
    agent_id: UUID,
    actor_id: UUID,
    status: AgentStatus,
    request_id: str | None,
) -> Agent:
    agent = await get_agent(session, organization_id, agent_id)
    before = agent_snapshot(agent)
    agent.status = status
    record_audit(
        session,
        organization_id=organization_id,
        actor_type=ActorType.USER,
        actor_id=actor_id,
        action=f"agent.{status.value}",
        target_type="agent",
        target_id=agent.id,
        before=before,
        after=agent_snapshot(agent),
        request_id=request_id,
    )
    await session.commit()
    await session.refresh(agent)
    return agent


async def issue_agent_credential(
    session: AsyncSession,
    *,
    organization_id: UUID,
    agent_id: UUID,
    actor_id: UUID,
    expires_at: datetime | None,
    rotate: bool,
    request_id: str | None,
) -> tuple[str, AgentCredential]:
    agent = await get_agent(session, organization_id, agent_id)
    if agent.status == AgentStatus.REVOKED:
        raise ValidationError("Credentials cannot be issued for a revoked agent")
    if expires_at is not None and expires_at <= datetime.now(UTC):
        raise ValidationError("Credential expiry must be in the future")

    active_credentials = list(
        (
            await session.scalars(
                select(AgentCredential).where(
                    AgentCredential.agent_id == agent.id,
                    AgentCredential.status == CredentialStatus.ACTIVE,
                )
            )
        ).all()
    )
    if active_credentials and not rotate:
        raise ConflictError("The agent already has an active credential; use rotate")

    now = datetime.now(UTC)
    if rotate:
        for existing in active_credentials:
            existing.status = CredentialStatus.REVOKED
            existing.revoked_at = now

    raw_credential, prefix, credential_hash = generate_agent_key()
    credential = AgentCredential(
        agent_id=agent.id,
        key_prefix=prefix,
        secret_hash=credential_hash,
        status=CredentialStatus.ACTIVE,
        expires_at=expires_at,
    )
    session.add(credential)
    await session.flush()
    record_audit(
        session,
        organization_id=organization_id,
        actor_type=ActorType.USER,
        actor_id=actor_id,
        action="agent.credential_rotate" if rotate else "agent.credential_create",
        target_type="agent",
        target_id=agent.id,
        details={
            "key_prefix": prefix,
            "expires_at": expires_at,
            "revoked_count": len(active_credentials),
        },
        request_id=request_id,
    )
    await session.commit()
    await session.refresh(credential)
    return raw_credential, credential
