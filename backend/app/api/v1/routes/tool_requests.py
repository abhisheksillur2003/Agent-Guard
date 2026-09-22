from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from backend.app.api.dependencies.auth import CurrentAgent, DatabaseSession, require_roles
from backend.app.api.dependencies.request import get_request_id
from backend.app.models import User, UserRole
from backend.app.schemas.decisions import DecisionResponse, ToolRequestEvaluation
from backend.app.services import policy_engine

router = APIRouter(prefix="/tool-requests", tags=["tool requests"])
DecisionReader = Annotated[
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


@router.post("/evaluate", response_model=DecisionResponse)
async def evaluate_tool_request(
    data: ToolRequestEvaluation,
    request: Request,
    agent: CurrentAgent,
    session: DatabaseSession,
) -> DecisionResponse:
    decision = await policy_engine.evaluate_tool_request(
        session,
        agent=agent,
        data=data,
        request_id=get_request_id(request),
    )
    return DecisionResponse.model_validate(decision)


@router.get("/decisions", response_model=list[DecisionResponse])
async def list_decisions(
    user: DecisionReader,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[DecisionResponse]:
    decisions = await policy_engine.list_decisions(session, user.organization_id, limit)
    return [DecisionResponse.model_validate(decision) for decision in decisions]


@router.get("/decisions/{decision_id}", response_model=DecisionResponse)
async def get_decision(
    decision_id: UUID,
    user: DecisionReader,
    session: DatabaseSession,
) -> DecisionResponse:
    decision = await policy_engine.get_decision(session, user.organization_id, decision_id)
    return DecisionResponse.model_validate(decision)
