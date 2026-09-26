from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from backend.app.api.dependencies.auth import DatabaseSession, require_roles
from backend.app.api.dependencies.request import get_request_id
from backend.app.models import User, UserRole
from backend.app.schemas.tools import ToolAdapterResponse, ToolCreate, ToolResponse, ToolUpdate
from backend.app.services import tools as tool_service

router = APIRouter(prefix="/tools", tags=["tools"])
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
ToolEditor = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.DEVELOPER))]


@router.post("", response_model=ToolResponse, status_code=status.HTTP_201_CREATED)
async def create_tool(
    data: ToolCreate,
    request: Request,
    user: ToolEditor,
    session: DatabaseSession,
) -> ToolResponse:
    tool = await tool_service.create_tool(
        session,
        organization_id=user.organization_id,
        actor_id=user.id,
        data=data,
        request_id=get_request_id(request),
    )
    return ToolResponse.model_validate(tool)


@router.get("", response_model=list[ToolResponse])
async def list_tools(user: AnyUser, session: DatabaseSession) -> list[ToolResponse]:
    tools = await tool_service.list_tools(session, user.organization_id)
    return [ToolResponse.model_validate(tool) for tool in tools]


@router.get("/adapters", response_model=list[ToolAdapterResponse])
async def list_tool_adapters(_user: AnyUser) -> list[ToolAdapterResponse]:
    return [
        ToolAdapterResponse(
            name=item.name,
            version=item.version,
            retry_safe=item.retry_safe,
            required_capabilities=list(item.required_capabilities),
            configured=item.configured,
        )
        for item in tool_service.list_tool_adapters()
    ]


@router.get("/{tool_id}", response_model=ToolResponse)
async def get_tool(tool_id: UUID, user: AnyUser, session: DatabaseSession) -> ToolResponse:
    tool = await tool_service.get_tool(session, user.organization_id, tool_id)
    return ToolResponse.model_validate(tool)


@router.patch("/{tool_id}", response_model=ToolResponse)
async def update_tool(
    tool_id: UUID,
    data: ToolUpdate,
    request: Request,
    user: ToolEditor,
    session: DatabaseSession,
) -> ToolResponse:
    tool = await tool_service.update_tool(
        session,
        organization_id=user.organization_id,
        tool_id=tool_id,
        actor_id=user.id,
        actor_role=user.role,
        data=data,
        request_id=get_request_id(request),
    )
    return ToolResponse.model_validate(tool)
