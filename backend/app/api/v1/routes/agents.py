from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from backend.app.api.dependencies.auth import DatabaseSession, require_roles
from backend.app.api.dependencies.request import get_request_id
from backend.app.models import AgentStatus, User, UserRole
from backend.app.schemas.agents import (
    AgentCreate,
    AgentCredentialResponse,
    AgentResponse,
    AgentUpdate,
    CredentialCreate,
)
from backend.app.services import agents as agent_service

router = APIRouter(prefix="/agents", tags=["agents"])
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
AgentEditor = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.DEVELOPER))]
Administrator = Annotated[User, Depends(require_roles(UserRole.ADMIN))]


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    data: AgentCreate,
    request: Request,
    user: AgentEditor,
    session: DatabaseSession,
) -> AgentResponse:
    agent = await agent_service.create_agent(
        session,
        organization_id=user.organization_id,
        actor_id=user.id,
        data=data,
        request_id=get_request_id(request),
    )
    return AgentResponse.model_validate(agent)


@router.get("", response_model=list[AgentResponse])
async def list_agents(user: AnyUser, session: DatabaseSession) -> list[AgentResponse]:
    agents = await agent_service.list_agents(session, user.organization_id)
    return [AgentResponse.model_validate(agent) for agent in agents]


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: UUID, user: AnyUser, session: DatabaseSession) -> AgentResponse:
    agent = await agent_service.get_agent(session, user.organization_id, agent_id)
    return AgentResponse.model_validate(agent)


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: UUID,
    data: AgentUpdate,
    request: Request,
    user: AgentEditor,
    session: DatabaseSession,
) -> AgentResponse:
    agent = await agent_service.update_agent(
        session,
        organization_id=user.organization_id,
        agent_id=agent_id,
        actor_id=user.id,
        data=data,
        request_id=get_request_id(request),
    )
    return AgentResponse.model_validate(agent)


@router.post("/{agent_id}/suspend", response_model=AgentResponse)
async def suspend_agent(
    agent_id: UUID,
    request: Request,
    user: Administrator,
    session: DatabaseSession,
) -> AgentResponse:
    agent = await agent_service.set_agent_status(
        session,
        organization_id=user.organization_id,
        agent_id=agent_id,
        actor_id=user.id,
        status=AgentStatus.SUSPENDED,
        request_id=get_request_id(request),
    )
    return AgentResponse.model_validate(agent)


@router.post("/{agent_id}/activate", response_model=AgentResponse)
async def activate_agent(
    agent_id: UUID,
    request: Request,
    user: Administrator,
    session: DatabaseSession,
) -> AgentResponse:
    agent = await agent_service.set_agent_status(
        session,
        organization_id=user.organization_id,
        agent_id=agent_id,
        actor_id=user.id,
        status=AgentStatus.ACTIVE,
        request_id=get_request_id(request),
    )
    return AgentResponse.model_validate(agent)


@router.post(
    "/{agent_id}/credentials",
    response_model=AgentCredentialResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_credential(
    agent_id: UUID,
    data: CredentialCreate,
    request: Request,
    user: AgentEditor,
    session: DatabaseSession,
) -> AgentCredentialResponse:
    raw, credential = await agent_service.issue_agent_credential(
        session,
        organization_id=user.organization_id,
        agent_id=agent_id,
        actor_id=user.id,
        expires_at=data.expires_at,
        rotate=False,
        request_id=get_request_id(request),
    )
    return AgentCredentialResponse(
        credential=raw,
        key_prefix=credential.key_prefix,
        expires_at=credential.expires_at,
    )


@router.post("/{agent_id}/credentials/rotate", response_model=AgentCredentialResponse)
async def rotate_credential(
    agent_id: UUID,
    data: CredentialCreate,
    request: Request,
    user: AgentEditor,
    session: DatabaseSession,
) -> AgentCredentialResponse:
    raw, credential = await agent_service.issue_agent_credential(
        session,
        organization_id=user.organization_id,
        agent_id=agent_id,
        actor_id=user.id,
        expires_at=data.expires_at,
        rotate=True,
        request_id=get_request_id(request),
    )
    return AgentCredentialResponse(
        credential=raw,
        key_prefix=credential.key_prefix,
        expires_at=credential.expires_at,
    )
