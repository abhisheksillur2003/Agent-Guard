from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="AGENTGUARD_",
        extra="ignore",
    )

    environment: Literal["local", "test", "ci", "staging", "production"] = "local"
    log_level: str = "INFO"
    database_url: str = Field(
        default="postgresql+asyncpg://agentguard:change-me-local-only@localhost:5432/agentguard",
        repr=False,
    )
    auth_signing_key: SecretStr = Field(
        default=SecretStr("local-development-signing-key-change-me"),
        repr=False,
    )
    agent_key_pepper: SecretStr = Field(
        default=SecretStr("local-development-agent-key-pepper-change-me"),
        repr=False,
    )
    finding_fingerprint_pepper: SecretStr = Field(
        default=SecretStr("local-development-finding-fingerprint-pepper-change-me"),
        repr=False,
    )
    access_token_minutes: int = Field(default=30, ge=5, le=1440)
    approval_ttl_hours: int = Field(default=24, ge=1, le=168)
    execution_decision_ttl_minutes: int = Field(default=15, ge=1, le=1440)
    redis_url: str = "redis://localhost:6379/0"
    stale_execution_seconds: int = Field(default=300, ge=30, le=86_400)
    service_version: str = "0.8.0"
    otel_service_name: str = "agentguard-api"
    otel_traces_endpoint: str | None = None

    @model_validator(mode="after")
    def reject_local_secrets_in_production(self) -> "Settings":
        if self.environment != "production":
            return self
        local_values = {
            "local-development-signing-key-change-me",
            "local-development-agent-key-pepper-change-me",
            "local-development-finding-fingerprint-pepper-change-me",
        }
        if (
            self.auth_signing_key.get_secret_value() in local_values
            or self.agent_key_pepper.get_secret_value() in local_values
            or self.finding_fingerprint_pepper.get_secret_value() in local_values
        ):
            raise ValueError("Production requires non-default authentication secrets")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
