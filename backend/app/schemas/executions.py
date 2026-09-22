from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.app.models.enums import ExecutionStatus
from backend.app.schemas.common import ORMModel


class ExecutionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: UUID
    arguments: dict[str, Any] = Field(default_factory=dict)


class ExecutionRetry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    arguments: dict[str, Any] = Field(default_factory=dict)


class ExecutionResponse(ORMModel):
    id: UUID
    organization_id: UUID
    decision_id: UUID
    approval_id: UUID | None
    agent_id: UUID
    tool_id: UUID
    operation: str
    environment: str
    status: ExecutionStatus
    adapter_name: str
    adapter_version: str
    result_summary: dict[str, Any]
    error_code: str | None
    attempt_count: int
    max_attempts: int
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime


class ExecutionEventResponse(ORMModel):
    id: UUID
    execution_id: UUID
    sequence: int
    event_type: str
    status: ExecutionStatus
    details_json: dict[str, Any]
    created_at: datetime
