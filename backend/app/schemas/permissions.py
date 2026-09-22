from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from backend.app.schemas.common import ORMModel


class PermissionUpsert(BaseModel):
    operations: list[str] = Field(min_length=1)
    constraints: dict[str, Any] = Field(default_factory=dict)

    @field_validator("operations")
    @classmethod
    def normalize_operations(cls, values: list[str]) -> list[str]:
        cleaned = sorted({value.strip().lower() for value in values if value.strip()})
        if not cleaned:
            raise ValueError("At least one operation is required")
        return cleaned


class PermissionResponse(ORMModel):
    id: UUID
    agent_id: UUID
    tool_id: UUID
    operations: list[str]
    constraints_json: dict[str, Any]
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class PermissionDecision(BaseModel):
    allowed: bool
    reason_code: str
    permission_id: UUID | None = None
    constraints: dict[str, Any] = Field(default_factory=dict)
