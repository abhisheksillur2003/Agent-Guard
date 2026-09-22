from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.errors import ConflictError, NotFoundError, ValidationError
from backend.app.models import ActorType, Agent, Policy, PolicyVersion, Tool
from backend.app.schemas.policies import (
    PolicyCreate,
    PolicyDocument,
    PolicyResponse,
    PolicyUpdate,
    PolicyVersionResponse,
)
from backend.app.services.audit import record_audit


async def _validate_scope(
    session: AsyncSession, organization_id: UUID, document: PolicyDocument
) -> None:
    if document.scope.agent_ids:
        agent_count = await session.scalar(
            select(func.count())
            .select_from(Agent)
            .where(
                Agent.organization_id == organization_id,
                Agent.id.in_(document.scope.agent_ids),
            )
        )
        if agent_count != len(document.scope.agent_ids):
            raise ValidationError("Every scoped agent must belong to the organization")
    if document.scope.tool_ids:
        tool_count = await session.scalar(
            select(func.count())
            .select_from(Tool)
            .where(
                Tool.organization_id == organization_id,
                Tool.id.in_(document.scope.tool_ids),
            )
        )
        if tool_count != len(document.scope.tool_ids):
            raise ValidationError("Every scoped tool must belong to the organization")


async def get_policy(session: AsyncSession, organization_id: UUID, policy_id: UUID) -> Policy:
    policy = await session.scalar(
        select(Policy).where(
            Policy.id == policy_id,
            Policy.organization_id == organization_id,
        )
    )
    if policy is None:
        raise NotFoundError("Policy")
    return policy


async def get_policy_version(session: AsyncSession, policy_id: UUID, version: int) -> PolicyVersion:
    policy_version = await session.scalar(
        select(PolicyVersion).where(
            PolicyVersion.policy_id == policy_id,
            PolicyVersion.version == version,
        )
    )
    if policy_version is None:
        raise NotFoundError("Policy version")
    return policy_version


async def list_policies(session: AsyncSession, organization_id: UUID) -> list[Policy]:
    result = await session.scalars(
        select(Policy)
        .where(Policy.organization_id == organization_id)
        .order_by(Policy.priority, Policy.name, Policy.id)
    )
    return list(result.all())


async def list_policy_versions(session: AsyncSession, policy_id: UUID) -> list[PolicyVersion]:
    result = await session.scalars(
        select(PolicyVersion)
        .where(PolicyVersion.policy_id == policy_id)
        .order_by(PolicyVersion.version.desc())
    )
    return list(result.all())


def version_response(version: PolicyVersion) -> PolicyVersionResponse:
    return PolicyVersionResponse(
        id=version.id,
        policy_id=version.policy_id,
        version=version.version,
        document=PolicyDocument.model_validate(version.document_json),
        created_by=version.created_by,
        created_at=version.created_at,
    )


async def policy_response(session: AsyncSession, policy: Policy) -> PolicyResponse:
    current = await get_policy_version(session, policy.id, policy.current_version)
    return PolicyResponse(
        id=policy.id,
        organization_id=policy.organization_id,
        name=policy.name,
        description=policy.description,
        status=policy.status,
        priority=policy.priority,
        current_version=policy.current_version,
        document=PolicyDocument.model_validate(current.document_json),
        created_by=policy.created_by,
        created_at=policy.created_at,
        updated_at=policy.updated_at,
    )


async def create_policy(
    session: AsyncSession,
    *,
    organization_id: UUID,
    actor_id: UUID,
    data: PolicyCreate,
    request_id: str | None,
) -> Policy:
    duplicate = await session.scalar(
        select(Policy.id).where(
            Policy.organization_id == organization_id,
            Policy.name == data.name,
        )
    )
    if duplicate is not None:
        raise ConflictError("A policy with this name already exists")
    await _validate_scope(session, organization_id, data.document)

    policy = Policy(
        organization_id=organization_id,
        name=data.name,
        description=data.description,
        priority=data.priority,
        current_version=1,
        created_by=actor_id,
    )
    session.add(policy)
    await session.flush()
    version = PolicyVersion(
        policy_id=policy.id,
        version=1,
        document_json=data.document.model_dump(mode="json"),
        created_by=actor_id,
    )
    session.add(version)
    await session.flush()
    record_audit(
        session,
        organization_id=organization_id,
        actor_type=ActorType.USER,
        actor_id=actor_id,
        action="policy.create",
        target_type="policy",
        target_id=policy.id,
        after={
            "name": policy.name,
            "status": policy.status,
            "priority": policy.priority,
            "version": 1,
            "document": version.document_json,
        },
        request_id=request_id,
    )
    await session.commit()
    await session.refresh(policy)
    return policy


async def update_policy(
    session: AsyncSession,
    *,
    organization_id: UUID,
    policy_id: UUID,
    actor_id: UUID,
    data: PolicyUpdate,
    request_id: str | None,
) -> Policy:
    changes = data.model_dump(exclude_unset=True)
    if not changes:
        raise ValidationError("At least one policy field must be provided")
    policy = await get_policy(session, organization_id, policy_id)
    before = {
        "name": policy.name,
        "description": policy.description,
        "status": policy.status,
        "priority": policy.priority,
        "version": policy.current_version,
    }
    if data.name is not None and data.name != policy.name:
        normalized_name = data.name.strip()
        duplicate = await session.scalar(
            select(Policy.id).where(
                Policy.organization_id == organization_id,
                Policy.name == normalized_name,
                Policy.id != policy.id,
            )
        )
        if duplicate is not None:
            raise ConflictError("A policy with this name already exists")
        policy.name = normalized_name
    if "description" in changes:
        policy.description = data.description
    if data.priority is not None:
        policy.priority = data.priority
    if data.status is not None:
        policy.status = data.status
    if data.document is not None:
        await _validate_scope(session, organization_id, data.document)
        policy.current_version += 1
        session.add(
            PolicyVersion(
                policy_id=policy.id,
                version=policy.current_version,
                document_json=data.document.model_dump(mode="json"),
                created_by=actor_id,
            )
        )
    await session.flush()
    record_audit(
        session,
        organization_id=organization_id,
        actor_type=ActorType.USER,
        actor_id=actor_id,
        action="policy.update",
        target_type="policy",
        target_id=policy.id,
        before=before,
        after={
            "name": policy.name,
            "description": policy.description,
            "status": policy.status,
            "priority": policy.priority,
            "version": policy.current_version,
        },
        request_id=request_id,
    )
    await session.commit()
    await session.refresh(policy)
    return policy
