from typing import Annotated

from fastapi import APIRouter, Depends, Request

from backend.app.api.dependencies.auth import DatabaseSession, require_roles
from backend.app.api.dependencies.request import get_request_id
from backend.app.core.config import get_settings
from backend.app.models import ActorType, User, UserRole
from backend.app.schemas.local_ai import (
    LocalAIClassificationRequest,
    LocalAIClassificationResponse,
    LocalAIStatusResponse,
)
from backend.app.services import local_ai as local_ai_service
from backend.app.services.audit import record_audit

router = APIRouter(prefix="/local-ai", tags=["local-ai"])
LocalAIViewer = Annotated[
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


@router.get("/status", response_model=LocalAIStatusResponse)
async def local_ai_status(_user: LocalAIViewer) -> LocalAIStatusResponse:
    return await local_ai_service.get_status(get_settings())


@router.post("/classify", response_model=LocalAIClassificationResponse)
async def classify_content(
    data: LocalAIClassificationRequest,
    request: Request,
    user: LocalAIViewer,
    session: DatabaseSession,
) -> LocalAIClassificationResponse:
    result = await local_ai_service.classify(get_settings(), data.content)
    record_audit(
        session,
        organization_id=user.organization_id,
        actor_type=ActorType.USER,
        actor_id=user.id,
        action="local_ai.classify",
        target_type="local_ai",
        target_id=None,
        details={
            "model": result.model,
            "advisory_only": True,
            "input_characters": len(data.content),
        },
        request_id=get_request_id(request),
    )
    await session.commit()
    return result
