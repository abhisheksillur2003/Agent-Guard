from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.models.enums import (
    DetectorKind,
    DetectorStatus,
    FindingAction,
    FindingSeverity,
)
from backend.app.schemas.common import ORMModel
from backend.app.schemas.policies import PolicyScope

REASON_PATTERN = r"^[A-Z][A-Z0-9_]{2,79}$"
SecretType = Literal[
    "aws_access_key",
    "jwt",
    "private_key",
    "generic_api_key",
    "high_entropy",
]
PiiType = Literal["email", "phone", "credit_card", "ipv4", "india_aadhaar"]
PromptRule = Literal[
    "ignore_instructions",
    "system_prompt_extraction",
    "tool_override",
    "role_impersonation",
]


class SecuritySchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DetectorDocumentBase(SecuritySchema):
    scope: PolicyScope = Field(default_factory=PolicyScope)
    action: FindingAction
    severity: FindingSeverity
    reason_code: str = Field(pattern=REASON_PATTERN, max_length=80)


class SecretDetectorDocument(DetectorDocumentBase):
    kind: Literal[DetectorKind.SECRET]
    secret_types: list[SecretType] = Field(min_length=1, max_length=5)
    minimum_entropy: float = Field(default=3.6, ge=3.0, le=6.0, allow_inf_nan=False)
    minimum_token_length: int = Field(default=24, ge=16, le=256)

    @field_validator("secret_types")
    @classmethod
    def unique_secret_types(cls, values: list[SecretType]) -> list[SecretType]:
        return list(dict.fromkeys(values))


class PiiDetectorDocument(DetectorDocumentBase):
    kind: Literal[DetectorKind.PII]
    entities: list[PiiType] = Field(min_length=1, max_length=5)

    @field_validator("entities")
    @classmethod
    def unique_entities(cls, values: list[PiiType]) -> list[PiiType]:
        return list(dict.fromkeys(values))


class PromptInjectionDetectorDocument(DetectorDocumentBase):
    kind: Literal[DetectorKind.PROMPT_INJECTION]
    rules: list[PromptRule] = Field(min_length=1, max_length=4)

    @field_validator("rules")
    @classmethod
    def unique_rules(cls, values: list[PromptRule]) -> list[PromptRule]:
        return list(dict.fromkeys(values))


DetectorDocument = Annotated[
    SecretDetectorDocument | PiiDetectorDocument | PromptInjectionDetectorDocument,
    Field(discriminator="kind"),
]


class DetectorCreate(SecuritySchema):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    priority: int = Field(default=100, ge=0, le=10000)
    document: DetectorDocument

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip()


class DetectorUpdate(SecuritySchema):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    priority: int | None = Field(default=None, ge=0, le=10000)
    status: DetectorStatus | None = None
    document: DetectorDocument | None = None


class DetectorVersionResponse(SecuritySchema):
    id: UUID
    detector_id: UUID
    version: int
    document: DetectorDocument
    created_by: UUID
    created_at: datetime


class DetectorResponse(SecuritySchema):
    id: UUID
    organization_id: UUID
    name: str
    description: str | None
    status: DetectorStatus
    priority: int
    current_version: int
    document: DetectorDocument
    created_by: UUID
    created_at: datetime
    updated_at: datetime


class SecurityFindingResponse(ORMModel):
    id: UUID
    organization_id: UUID
    decision_id: UUID
    detector_id: UUID
    detector_version_id: UUID
    detector_kind: DetectorKind
    category: str
    severity: FindingSeverity
    action: FindingAction
    reason_code: str
    location: str
    occurrence_count: int
    created_at: datetime
