from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from backend.app.models.enums import RiskTier, ToolCapability, ToolStatus
from backend.app.schemas.common import ORMModel


def empty_capabilities() -> list[ToolCapability]:
    return []


class ToolCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    input_schema: dict[str, Any]
    risk_class: RiskTier
    capability_flags: list[ToolCapability] = Field(default_factory=empty_capabilities)
    adapter_name: str = Field(default="safe_echo", min_length=2, max_length=80)
    adapter_version: str = Field(default="1", min_length=1, max_length=40)
    execution_timeout_seconds: int = Field(default=10, ge=1, le=60)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()


class ToolUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    input_schema: dict[str, Any] | None = None
    risk_class: RiskTier | None = None
    capability_flags: list[ToolCapability] | None = None
    status: ToolStatus | None = None
    adapter_name: str | None = Field(default=None, min_length=2, max_length=80)
    adapter_version: str | None = Field(default=None, min_length=1, max_length=40)
    execution_timeout_seconds: int | None = Field(default=None, ge=1, le=60)


class ToolResponse(ORMModel):
    id: UUID
    organization_id: UUID
    name: str
    description: str | None
    input_schema: dict[str, Any]
    risk_class: RiskTier
    capability_flags: list[ToolCapability]
    status: ToolStatus
    adapter_name: str
    adapter_version: str
    execution_timeout_seconds: int
    created_at: datetime
    updated_at: datetime


class ToolAdapterResponse(BaseModel):
    name: str
    version: str
    retry_safe: bool
    required_capabilities: list[ToolCapability]
    configured: bool
