from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from backend.app.models.enums import AgentStatus, RiskTier
from backend.app.schemas.common import ORMModel
from backend.app.schemas.reliability import ReliabilityBudget


class AgentCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    owner_user_id: UUID | None = None
    risk_tier: RiskTier = RiskTier.MEDIUM
    allowed_environments: list[str] = Field(default_factory=lambda: ["local"])
    budget_config: ReliabilityBudget = Field(default_factory=ReliabilityBudget)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("allowed_environments")
    @classmethod
    def normalize_environments(cls, values: list[str]) -> list[str]:
        cleaned = sorted({value.strip().lower() for value in values if value.strip()})
        if not cleaned:
            raise ValueError("At least one environment is required")
        return cleaned


class AgentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    owner_user_id: UUID | None = None
    risk_tier: RiskTier | None = None
    allowed_environments: list[str] | None = None
    budget_config: ReliabilityBudget | None = None


class AgentResponse(ORMModel):
    id: UUID
    organization_id: UUID
    name: str
    description: str | None
    owner_user_id: UUID | None
    status: AgentStatus
    risk_tier: RiskTier
    allowed_environments: list[str]
    budget_config: ReliabilityBudget
    created_at: datetime
    updated_at: datetime


class CredentialCreate(BaseModel):
    expires_at: datetime | None = None

    @field_validator("expires_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("Credential expiry must include a timezone")
        return value


class AgentCredentialResponse(BaseModel):
    credential: str
    key_prefix: str
    expires_at: datetime | None
    warning: str = "Store this credential now. It will not be shown again."


class AgentPrincipalResponse(ORMModel):
    id: UUID
    organization_id: UUID
    name: str
    status: AgentStatus
