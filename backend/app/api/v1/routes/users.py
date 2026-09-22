from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from backend.app.api.dependencies.auth import DatabaseSession, require_roles
from backend.app.api.dependencies.request import get_request_id
from backend.app.models import User, UserRole
from backend.app.schemas.users import UserCreate, UserResponse, UserUpdate
from backend.app.services import users as user_service

router = APIRouter(prefix="/users", tags=["users"])
Administrator = Annotated[User, Depends(require_roles(UserRole.ADMIN))]


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    data: UserCreate,
    request: Request,
    administrator: Administrator,
    session: DatabaseSession,
) -> UserResponse:
    user = await user_service.create_user(
        session,
        organization_id=administrator.organization_id,
        actor_id=administrator.id,
        data=data,
        request_id=get_request_id(request),
    )
    return UserResponse.model_validate(user)


@router.get("", response_model=list[UserResponse])
async def list_users(
    administrator: Administrator,
    session: DatabaseSession,
) -> list[UserResponse]:
    users = await user_service.list_users(session, administrator.organization_id)
    return [UserResponse.model_validate(user) for user in users]


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    administrator: Administrator,
    session: DatabaseSession,
) -> UserResponse:
    user = await user_service.get_user(session, administrator.organization_id, user_id)
    return UserResponse.model_validate(user)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    data: UserUpdate,
    request: Request,
    administrator: Administrator,
    session: DatabaseSession,
) -> UserResponse:
    user = await user_service.update_user(
        session,
        organization_id=administrator.organization_id,
        user_id=user_id,
        actor_id=administrator.id,
        data=data,
        request_id=get_request_id(request),
    )
    return UserResponse.model_validate(user)
