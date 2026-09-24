from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LocalAIStatusResponse(BaseModel):
    available: bool
    model: str
    model_available: bool
    installed_models: list[str]
    advisory_only: Literal[True] = True


class LocalAIClassificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=8_000)


class LocalAIClassificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risk_level: Literal["low", "medium", "high", "critical"]
    confidence: float = Field(ge=0.0, le=1.0)
    categories: list[str] = Field(default_factory=list, max_length=8)
    rationale: str = Field(min_length=1, max_length=500)


class LocalAIClassificationResponse(LocalAIClassificationResult):
    model: str
    advisory_only: Literal[True] = True
