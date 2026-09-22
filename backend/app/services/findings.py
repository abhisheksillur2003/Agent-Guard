from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.errors import NotFoundError
from backend.app.models import (
    DetectorKind,
    FindingAction,
    FindingSeverity,
    SecurityFinding,
)


async def list_findings(
    session: AsyncSession,
    organization_id: UUID,
    *,
    decision_id: UUID | None,
    detector_kind: DetectorKind | None,
    severity: FindingSeverity | None,
    action: FindingAction | None,
    limit: int,
) -> list[SecurityFinding]:
    statement = select(SecurityFinding).where(SecurityFinding.organization_id == organization_id)
    if decision_id is not None:
        statement = statement.where(SecurityFinding.decision_id == decision_id)
    if detector_kind is not None:
        statement = statement.where(SecurityFinding.detector_kind == detector_kind)
    if severity is not None:
        statement = statement.where(SecurityFinding.severity == severity)
    if action is not None:
        statement = statement.where(SecurityFinding.action == action)
    result = await session.scalars(
        statement.order_by(SecurityFinding.created_at.desc()).limit(limit)
    )
    return list(result.all())


async def get_finding(
    session: AsyncSession, organization_id: UUID, finding_id: UUID
) -> SecurityFinding:
    finding = await session.scalar(
        select(SecurityFinding).where(
            SecurityFinding.id == finding_id,
            SecurityFinding.organization_id == organization_id,
        )
    )
    if finding is None:
        raise NotFoundError("Security finding")
    return finding
