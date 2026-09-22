from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from backend.app.models.enums import ApprovalStatus
from backend.app.schemas.common import ORMModel


class ApprovalAction(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


class ApprovalResponse(ORMModel):
    id: UUID
    organization_id: UUID
    decision_id: UUID
    agent_id: UUID
    requested_tool_id: UUID
    status: ApprovalStatus
    expires_at: datetime
    decided_at: datetime | None
    decided_by: UUID | None
    decision_reason: str | None
    created_at: datetime
    updated_at: datetime
