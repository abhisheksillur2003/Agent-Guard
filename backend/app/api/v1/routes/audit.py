from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from backend.app.api.dependencies.auth import DatabaseSession, require_roles
from backend.app.models import AuditLog, User, UserRole
from backend.app.schemas.audit import AuditLogResponse

router = APIRouter(prefix="/audit", tags=["audit"])
AuditViewer = Annotated[
    User,
    Depends(
        require_roles(
            UserRole.ADMIN,
            UserRole.DEVELOPER,
            UserRole.APPROVER,
            UserRole.READ_ONLY,
        )
    ),
]


@router.get("", response_model=list[AuditLogResponse])
async def list_audit_events(
    user: AuditViewer,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[AuditLogResponse]:
    events = list(
        (
            await session.scalars(
                select(AuditLog)
                .where(AuditLog.organization_id == user.organization_id)
                .order_by(AuditLog.created_at.desc())
                .limit(limit)
            )
        ).all()
    )
    return [AuditLogResponse.model_validate(event) for event in events]
