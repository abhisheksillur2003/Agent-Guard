from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from backend.app.api.dependencies.auth import DatabaseSession, require_roles
from backend.app.api.dependencies.request import get_request_id
from backend.app.models import ApprovalStatus, User, UserRole
from backend.app.schemas.approvals import ApprovalAction, ApprovalResponse
from backend.app.services import approvals as approval_service

router = APIRouter(prefix="/approvals", tags=["approvals"])
ApprovalViewer = Annotated[
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
Approver = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.APPROVER))]
Administrator = Annotated[User, Depends(require_roles(UserRole.ADMIN))]


@router.get("", response_model=list[ApprovalResponse])
async def list_approvals(
    request: Request,
    user: ApprovalViewer,
    session: DatabaseSession,
    status: Annotated[ApprovalStatus | None, Query()] = None,
    decision_id: Annotated[UUID | None, Query()] = None,
) -> list[ApprovalResponse]:
    approvals = await approval_service.list_approvals(
        session,
        user.organization_id,
        status=status,
        decision_id=decision_id,
        request_id=get_request_id(request),
    )
    return [ApprovalResponse.model_validate(item) for item in approvals]


@router.get("/{approval_id}", response_model=ApprovalResponse)
async def get_approval(
    approval_id: UUID,
    request: Request,
    user: ApprovalViewer,
    session: DatabaseSession,
) -> ApprovalResponse:
    approval = await approval_service.get_approval(
        session,
        user.organization_id,
        approval_id,
        request_id=get_request_id(request),
    )
    return ApprovalResponse.model_validate(approval)


@router.post("/{approval_id}/approve", response_model=ApprovalResponse)
async def approve_request(
    approval_id: UUID,
    data: ApprovalAction,
    request: Request,
    user: Approver,
    session: DatabaseSession,
) -> ApprovalResponse:
    approval = await approval_service.decide_approval(
        session,
        organization_id=user.organization_id,
        approval_id=approval_id,
        actor_id=user.id,
        status=ApprovalStatus.APPROVED,
        reason=data.reason,
        request_id=get_request_id(request),
    )
    return ApprovalResponse.model_validate(approval)


@router.post("/{approval_id}/reject", response_model=ApprovalResponse)
async def reject_request(
    approval_id: UUID,
    data: ApprovalAction,
    request: Request,
    user: Approver,
    session: DatabaseSession,
) -> ApprovalResponse:
    approval = await approval_service.decide_approval(
        session,
        organization_id=user.organization_id,
        approval_id=approval_id,
        actor_id=user.id,
        status=ApprovalStatus.REJECTED,
        reason=data.reason,
        request_id=get_request_id(request),
    )
    return ApprovalResponse.model_validate(approval)


@router.post("/{approval_id}/cancel", response_model=ApprovalResponse)
async def cancel_request(
    approval_id: UUID,
    data: ApprovalAction,
    request: Request,
    user: Administrator,
    session: DatabaseSession,
) -> ApprovalResponse:
    approval = await approval_service.cancel_approval(
        session,
        organization_id=user.organization_id,
        approval_id=approval_id,
        actor_id=user.id,
        reason=data.reason,
        request_id=get_request_id(request),
    )
    return ApprovalResponse.model_validate(approval)
