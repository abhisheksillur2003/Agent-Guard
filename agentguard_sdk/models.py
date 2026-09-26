import json
from datetime import datetime
from enum import StrEnum
from typing import Any, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SDKModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class DecisionOutcome(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


class ExecutionStatus(StrEnum):
    AUTHORIZED = "authorized"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


class GuardedResultStatus(StrEnum):
    EXECUTED = "executed"
    DENIED = "denied"
    APPROVAL_REQUIRED = "approval_required"


class ToolRequest(SDKModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

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

    @field_validator("arguments")
    @classmethod
    def require_json_arguments(cls, value: dict[str, Any]) -> dict[str, Any]:
        try:
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("Arguments must contain finite JSON values") from exc
        return value


class PolicyMatch(SDKModel):
    policy_id: UUID
    policy_version_id: UUID
    version: int
    effect: str
    reason_code: str


class Decision(SDKModel):
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


class Execution(SDKModel):
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


class GuardedResult(SDKModel):
    status: GuardedResultStatus
    decision: Decision
    execution: Execution | None = None

    @model_validator(mode="after")
    def validate_execution_state(self) -> Self:
        expected = {
            DecisionOutcome.ALLOW: GuardedResultStatus.EXECUTED,
            DecisionOutcome.DENY: GuardedResultStatus.DENIED,
            DecisionOutcome.REQUIRE_APPROVAL: GuardedResultStatus.APPROVAL_REQUIRED,
        }[self.decision.outcome]
        if self.status != expected:
            raise ValueError("Guarded result status does not match the policy decision")
        if (self.execution is not None) != (self.status == GuardedResultStatus.EXECUTED):
            raise ValueError("Only an executed result may contain an execution")
        return self
