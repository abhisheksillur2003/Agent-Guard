from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.models.enums import PolicyEffect, PolicyStatus

PATH_PATTERN = r"^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*$"
REASON_PATTERN = r"^[A-Z][A-Z0-9_]{2,79}$"


class PolicySchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FieldMissingCondition(PolicySchema):
    type: Literal["field_missing"]
    path: str = Field(pattern=PATH_PATTERN, max_length=240)


class NumberGreaterThanCondition(PolicySchema):
    type: Literal["number_gt"]
    path: str = Field(pattern=PATH_PATTERN, max_length=240)
    value: float = Field(allow_inf_nan=False)


class ValueInCondition(PolicySchema):
    type: Literal["value_in"]
    path: str = Field(pattern=PATH_PATTERN, max_length=240)
    values: list[Any] = Field(min_length=1, max_length=100)


class UtcHourOutsideCondition(PolicySchema):
    type: Literal["utc_hour_outside"]
    start_hour: int = Field(ge=0, le=23)
    end_hour: int = Field(ge=0, le=23)

    @model_validator(mode="after")
    def reject_empty_window(self) -> "UtcHourOutsideCondition":
        if self.start_hour == self.end_hour:
            raise ValueError("UTC time window must span at least one hour")
        return self


PolicyCondition = Annotated[
    FieldMissingCondition | NumberGreaterThanCondition | ValueInCondition | UtcHourOutsideCondition,
    Field(discriminator="type"),
]


def empty_uuid_list() -> list[UUID]:
    return []


def empty_condition_list() -> list[PolicyCondition]:
    return []


class PolicyScope(PolicySchema):
    agent_ids: list[UUID] = Field(default_factory=empty_uuid_list)
    tool_ids: list[UUID] = Field(default_factory=empty_uuid_list)
    environments: list[str] = Field(default_factory=list)
    operations: list[str] = Field(default_factory=list)

    @field_validator("agent_ids", "tool_ids")
    @classmethod
    def unique_ids(cls, values: list[UUID]) -> list[UUID]:
        return sorted(set(values), key=str)

    @field_validator("environments", "operations")
    @classmethod
    def normalize_names(cls, values: list[str]) -> list[str]:
        return sorted({value.strip().lower() for value in values if value.strip()})


class PolicyDocument(PolicySchema):
    scope: PolicyScope = Field(default_factory=PolicyScope)
    effect: PolicyEffect
    reason_code: str = Field(pattern=REASON_PATTERN, max_length=80)
    conditions: list[PolicyCondition] = Field(default_factory=empty_condition_list, max_length=50)


class PolicyCreate(PolicySchema):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    priority: int = Field(default=100, ge=0, le=10000)
    document: PolicyDocument

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()


class PolicyUpdate(PolicySchema):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    priority: int | None = Field(default=None, ge=0, le=10000)
    status: PolicyStatus | None = None
    document: PolicyDocument | None = None


class PolicyVersionResponse(PolicySchema):
    id: UUID
    policy_id: UUID
    version: int
    document: PolicyDocument
    created_by: UUID
    created_at: datetime


class PolicyResponse(PolicySchema):
    id: UUID
    organization_id: UUID
    name: str
    description: str | None
    status: PolicyStatus
    priority: int
    current_version: int
    document: PolicyDocument
    created_by: UUID
    created_at: datetime
    updated_at: datetime
