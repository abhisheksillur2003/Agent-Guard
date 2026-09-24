from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.errors import AuthorizationError, ConflictError, NotFoundError
from backend.app.core.observability import record_approval_transition
from backend.app.models import ActorType, Agent, ApprovalRequest, ApprovalStatus
from backend.app.services.audit import record_audit


async def _expire_if_needed(
    session: AsyncSession,
    approval: ApprovalRequest,
    *,
    request_id: str | None = None,
) -> bool:
    if approval.status != ApprovalStatus.PENDING or approval.expires_at > datetime.now(UTC):
        return False
    approval.status = ApprovalStatus.EXPIRED
    approval.decided_at = datetime.now(UTC)
    approval.decision_reason = "Approval window expired"
    record_audit(
        session,
        organization_id=approval.organization_id,
        actor_type=ActorType.SYSTEM,
        actor_id=None,
        action="approval.expire",
        target_type="approval_request",
        target_id=approval.id,
        before={"status": ApprovalStatus.PENDING},
        after={"status": ApprovalStatus.EXPIRED},
        request_id=request_id,
    )
    return True


async def get_approval(
    session: AsyncSession,
    organization_id: UUID,
    approval_id: UUID,
    *,
    request_id: str | None = None,
) -> ApprovalRequest:
    approval = await session.scalar(
        select(ApprovalRequest).where(
            ApprovalRequest.id == approval_id,
            ApprovalRequest.organization_id == organization_id,
        )
    )
    if approval is None:
        raise NotFoundError("Approval request")
    if await _expire_if_needed(session, approval, request_id=request_id):
        await session.commit()
        await session.refresh(approval)
    return approval


async def list_approvals(
    session: AsyncSession,
    organization_id: UUID,
    *,
    status: ApprovalStatus | None,
    decision_id: UUID | None,
    request_id: str | None = None,
) -> list[ApprovalRequest]:
    expired_candidates = list(
        (
            await session.scalars(
                select(ApprovalRequest).where(
                    ApprovalRequest.organization_id == organization_id,
                    ApprovalRequest.status == ApprovalStatus.PENDING,
                    ApprovalRequest.expires_at <= datetime.now(UTC),
                )
            )
        ).all()
    )
    for candidate in expired_candidates:
        await _expire_if_needed(session, candidate, request_id=request_id)
    if expired_candidates:
        await session.commit()

    statement = select(ApprovalRequest).where(ApprovalRequest.organization_id == organization_id)
    if status is not None:
        statement = statement.where(ApprovalRequest.status == status)
    if decision_id is not None:
        statement = statement.where(ApprovalRequest.decision_id == decision_id)
    return list(
        (await session.scalars(statement.order_by(ApprovalRequest.created_at.desc()))).all()
    )


async def decide_approval(
    session: AsyncSession,
    *,
    organization_id: UUID,
    approval_id: UUID,
    actor_id: UUID,
    status: ApprovalStatus,
    reason: str,
    request_id: str | None,
) -> ApprovalRequest:
    approval = await session.scalar(
        select(ApprovalRequest)
        .where(
            ApprovalRequest.id == approval_id,
            ApprovalRequest.organization_id == organization_id,
        )
        .with_for_update()
    )
    if approval is None:
        raise NotFoundError("Approval request")
    if await _expire_if_needed(session, approval, request_id=request_id):
        await session.commit()
        record_approval_transition(ApprovalStatus.EXPIRED)
        raise ConflictError("Approval request has expired")
    if approval.status != ApprovalStatus.PENDING:
        raise ConflictError("Approval request has already been decided")
    if status != ApprovalStatus.CANCELLED:
        agent_owner = await session.scalar(
            select(Agent.owner_user_id).where(
                Agent.id == approval.agent_id,
                Agent.organization_id == organization_id,
            )
        )
        if agent_owner == actor_id:
            raise AuthorizationError("An agent owner cannot approve or reject its own request")

    approval.status = status
    approval.decided_at = datetime.now(UTC)
    approval.decided_by = actor_id
    approval.decision_reason = reason.strip()
    record_audit(
        session,
        organization_id=organization_id,
        actor_type=ActorType.USER,
        actor_id=actor_id,
        action=f"approval.{status.value}",
        target_type="approval_request",
        target_id=approval.id,
        before={"status": ApprovalStatus.PENDING},
        after={"status": status, "reason": approval.decision_reason},
        request_id=request_id,
    )
    await session.commit()
    await session.refresh(approval)
    record_approval_transition(status)
    return approval


async def cancel_approval(
    session: AsyncSession,
    *,
    organization_id: UUID,
    approval_id: UUID,
    actor_id: UUID,
    reason: str,
    request_id: str | None,
) -> ApprovalRequest:
    return await decide_approval(
        session,
        organization_id=organization_id,
        approval_id=approval_id,
        actor_id=actor_id,
        status=ApprovalStatus.CANCELLED,
        reason=reason,
        request_id=request_id,
    )
