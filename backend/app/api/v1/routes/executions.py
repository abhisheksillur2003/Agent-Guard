from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from backend.app.api.dependencies.auth import CurrentAgent, DatabaseSession, require_roles
from backend.app.api.dependencies.request import get_request_id
from backend.app.models import User, UserRole
from backend.app.schemas.executions import (
    ExecutionCreate,
    ExecutionEventResponse,
    ExecutionResponse,
    ExecutionRetry,
)
from backend.app.services import executions as execution_service

router = APIRouter(prefix="/executions", tags=["executions"])
ExecutionViewer = Annotated[
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


@router.post("", response_model=ExecutionResponse)
async def create_execution(
    data: ExecutionCreate,
    request: Request,
    agent: CurrentAgent,
    session: DatabaseSession,
) -> ExecutionResponse:
    execution = await execution_service.execute_tool_request(
        session,
        agent=agent,
        decision_id=data.decision_id,
        arguments=data.arguments,
        request_id=get_request_id(request),
    )
    return ExecutionResponse.model_validate(execution)


@router.get("", response_model=list[ExecutionResponse])
async def list_executions(
    user: ExecutionViewer,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[ExecutionResponse]:
    executions = await execution_service.list_executions(session, user.organization_id, limit)
    return [ExecutionResponse.model_validate(item) for item in executions]


@router.post("/{execution_id}/retry", response_model=ExecutionResponse)
async def retry_execution(
    execution_id: UUID,
    data: ExecutionRetry,
    request: Request,
    agent: CurrentAgent,
    session: DatabaseSession,
) -> ExecutionResponse:
    execution = await execution_service.retry_tool_execution(
        session,
        agent=agent,
        execution_id=execution_id,
        arguments=data.arguments,
        request_id=get_request_id(request),
    )
    return ExecutionResponse.model_validate(execution)


@router.get("/{execution_id}", response_model=ExecutionResponse)
async def get_execution(
    execution_id: UUID,
    user: ExecutionViewer,
    session: DatabaseSession,
) -> ExecutionResponse:
    execution = await execution_service.get_execution(session, user.organization_id, execution_id)
    return ExecutionResponse.model_validate(execution)


@router.get("/{execution_id}/events", response_model=list[ExecutionEventResponse])
async def list_execution_events(
    execution_id: UUID,
    user: ExecutionViewer,
    session: DatabaseSession,
) -> list[ExecutionEventResponse]:
    events = await execution_service.list_execution_events(
        session, user.organization_id, execution_id
    )
    return [ExecutionEventResponse.model_validate(item) for item in events]
