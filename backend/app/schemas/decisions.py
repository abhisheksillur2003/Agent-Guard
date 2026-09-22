from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.models.enums import DecisionOutcome
from backend.app.schemas.common import ORMModel


class ToolRequestEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_id: UUID
    operation: str = Field(min_length=1, max_length=120)
    environment: str = Field(min_length=1, max_length=80)
    arguments: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(
        min_length=8,
        max_length=120,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]+$",
    )

    @field_validator("operation", "environment")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip().lower()


class PolicyMatch(BaseModel):
    policy_id: UUID
    policy_version_id: UUID
    version: int
    effect: str
    reason_code: str


class DecisionResponse(ORMModel):
    id: UUID
    organization_id: UUID
    agent_id: UUID
    requested_tool_id: UUID
    operation: str
    environment: str
    idempotency_key: str
    request_id: str | None
    outcome: DecisionOutcome
    reason_code: str
    permission_id: UUID | None
    matched_policy_versions: list[PolicyMatch]
    evidence_json: dict[str, Any]
    created_at: datetime
