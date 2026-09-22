from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from backend.app.api.dependencies.auth import DatabaseSession, require_roles
from backend.app.api.dependencies.request import get_request_id
from backend.app.models import User, UserRole
from backend.app.schemas.common import MessageResponse
from backend.app.schemas.permissions import PermissionResponse, PermissionUpsert
from backend.app.services import permissions as permission_service

router = APIRouter(prefix="/agents/{agent_id}/permissions", tags=["permissions"])
AnyUser = Annotated[
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
Administrator = Annotated[User, Depends(require_roles(UserRole.ADMIN))]


@router.get("", response_model=list[PermissionResponse])
async def list_permissions(
    agent_id: UUID, user: AnyUser, session: DatabaseSession
) -> list[PermissionResponse]:
    permissions = await permission_service.list_permissions(session, user.organization_id, agent_id)
    return [PermissionResponse.model_validate(item) for item in permissions]


@router.put("/{tool_id}", response_model=PermissionResponse)
async def upsert_permission(
    agent_id: UUID,
    tool_id: UUID,
    data: PermissionUpsert,
    request: Request,
    user: Administrator,
    session: DatabaseSession,
) -> PermissionResponse:
    permission = await permission_service.upsert_permission(
        session,
        organization_id=user.organization_id,
        agent_id=agent_id,
        tool_id=tool_id,
        actor_id=user.id,
        data=data,
        request_id=get_request_id(request),
    )
    return PermissionResponse.model_validate(permission)


@router.delete("/{tool_id}", response_model=MessageResponse, status_code=status.HTTP_200_OK)
async def remove_permission(
    agent_id: UUID,
    tool_id: UUID,
    request: Request,
    user: Administrator,
    session: DatabaseSession,
) -> MessageResponse:
    await permission_service.remove_permission(
        session,
        organization_id=user.organization_id,
        agent_id=agent_id,
        tool_id=tool_id,
        actor_id=user.id,
        request_id=get_request_id(request),
    )
    return MessageResponse(message="Permission removed")
