from pydantic import BaseModel, ConfigDict, Field


class ReliabilityBudget(BaseModel):
    """Bounded, deterministic controls applied to one agent."""

    model_config = ConfigDict(extra="forbid")

    max_decisions_per_minute: int = Field(default=60, ge=1, le=10_000)
    max_executions_per_day: int = Field(default=1_000, ge=1, le=1_000_000)
    max_identical_requests_in_window: int = Field(default=5, ge=1, le=1_000)
    loop_detection_window_seconds: int = Field(default=60, ge=10, le=3_600)
    max_execution_attempts: int = Field(default=1, ge=1, le=5)
    retry_backoff_seconds: int = Field(default=5, ge=0, le=3_600)
