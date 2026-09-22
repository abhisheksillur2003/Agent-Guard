from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from backend.app.api.dependencies.auth import DatabaseSession, require_roles
from backend.app.api.dependencies.request import get_request_id
from backend.app.models import User, UserRole
from backend.app.schemas.policies import (
    PolicyCreate,
    PolicyResponse,
    PolicyUpdate,
    PolicyVersionResponse,
)
from backend.app.services import policies as policy_service

router = APIRouter(prefix="/policies", tags=["policies"])
PolicyReader = Annotated[
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


@router.post("", response_model=PolicyResponse, status_code=status.HTTP_201_CREATED)
async def create_policy(
    data: PolicyCreate,
    request: Request,
    administrator: Administrator,
    session: DatabaseSession,
) -> PolicyResponse:
    policy = await policy_service.create_policy(
        session,
        organization_id=administrator.organization_id,
        actor_id=administrator.id,
        data=data,
        request_id=get_request_id(request),
    )
    return await policy_service.policy_response(session, policy)


@router.get("", response_model=list[PolicyResponse])
async def list_policies(
    user: PolicyReader,
    session: DatabaseSession,
) -> list[PolicyResponse]:
    policies = await policy_service.list_policies(session, user.organization_id)
    return [await policy_service.policy_response(session, policy) for policy in policies]


@router.get("/{policy_id}", response_model=PolicyResponse)
async def get_policy(
    policy_id: UUID,
    user: PolicyReader,
    session: DatabaseSession,
) -> PolicyResponse:
    policy = await policy_service.get_policy(session, user.organization_id, policy_id)
    return await policy_service.policy_response(session, policy)


@router.patch("/{policy_id}", response_model=PolicyResponse)
async def update_policy(
    policy_id: UUID,
    data: PolicyUpdate,
    request: Request,
    administrator: Administrator,
    session: DatabaseSession,
) -> PolicyResponse:
    policy = await policy_service.update_policy(
        session,
        organization_id=administrator.organization_id,
        policy_id=policy_id,
        actor_id=administrator.id,
        data=data,
        request_id=get_request_id(request),
    )
    return await policy_service.policy_response(session, policy)


@router.get("/{policy_id}/versions", response_model=list[PolicyVersionResponse])
async def list_policy_versions(
    policy_id: UUID,
    user: PolicyReader,
    session: DatabaseSession,
) -> list[PolicyVersionResponse]:
    policy = await policy_service.get_policy(session, user.organization_id, policy_id)
    versions = await policy_service.list_policy_versions(session, policy.id)
    return [policy_service.version_response(version) for version in versions]
