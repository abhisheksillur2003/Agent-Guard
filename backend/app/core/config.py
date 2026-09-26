from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

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
    api_docs_enabled: bool = True
    allowed_hosts: list[str] = Field(
        default_factory=lambda: ["127.0.0.1", "localhost", "test", "testserver"]
    )
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
    service_version: str = "0.11.0"
    otel_service_name: str = "agentguard-api"
    otel_traces_endpoint: str | None = None
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2:3b"
    ollama_timeout_seconds: float = Field(default=60.0, ge=1.0, le=300.0)
    local_ai_enabled: bool = True
    http_webhook_enabled: bool = False
    http_webhook_allowed_urls: list[str] = Field(default_factory=list)
    http_webhook_bearer_tokens: dict[str, SecretStr] = Field(default_factory=dict, repr=False)
    http_webhook_allow_private_networks: bool = False
    http_webhook_max_response_bytes: int = Field(default=65_536, ge=0, le=1_048_576)

    @model_validator(mode="after")
    def reject_local_secrets_in_production(self) -> "Settings":
        allowed_webhook_urls = set(self.http_webhook_allowed_urls)
        if len(allowed_webhook_urls) != len(self.http_webhook_allowed_urls):
            raise ValueError("HTTP webhook allowlist entries must be unique")
        if self.http_webhook_enabled and not allowed_webhook_urls:
            raise ValueError("Enabled HTTP webhook adapter requires an explicit URL allowlist")
        if self.http_webhook_bearer_tokens and not self.http_webhook_enabled:
            raise ValueError("HTTP webhook bearer tokens require the adapter to be enabled")
        if not set(self.http_webhook_bearer_tokens).issubset(allowed_webhook_urls):
            raise ValueError("HTTP webhook bearer tokens must reference allowlisted URLs")
        for url in allowed_webhook_urls:
            try:
                parsed = urlsplit(url)
                port = parsed.port
            except ValueError as exc:
                raise ValueError("HTTP webhook allowlist contains an invalid URL") from exc
            if (
                parsed.scheme not in {"http", "https"}
                or parsed.hostname is None
                or parsed.username is not None
                or parsed.password is not None
                or parsed.query
                or parsed.fragment
                or port is not None
                and not 1 <= port <= 65_535
            ):
                raise ValueError(
                    "HTTP webhook URLs require HTTP(S), a host, and no credentials, query, or fragment"
                )
            if self.environment == "production" and parsed.scheme != "https":
                raise ValueError("Production HTTP webhook URLs must use HTTPS")
        for token in self.http_webhook_bearer_tokens.values():
            value = token.get_secret_value()
            if len(value) < 32 or "change-me" in value.lower() or "replace-with" in value.lower():
                raise ValueError(
                    "HTTP webhook bearer tokens must contain at least 32 non-placeholder characters"
                )

        if self.environment != "production":
            return self

        def credential_from_url(url: str, service: str) -> str:
            try:
                password = urlsplit(url).password
            except ValueError as exc:
                raise ValueError(f"Production {service} URL must be valid") from exc
            if (
                password is None
                or len(password) < 32
                or "change-me" in password.lower()
                or "replace-with" in password.lower()
            ):
                raise ValueError(
                    f"Production requires a non-placeholder {service} password "
                    "of at least 32 characters"
                )
            return password

        application_secrets = [
            self.auth_signing_key.get_secret_value(),
            self.agent_key_pepper.get_secret_value(),
            self.finding_fingerprint_pepper.get_secret_value(),
        ]
        forbidden_values = {
            "local-development-signing-key-change-me",
            "local-development-agent-key-pepper-change-me",
            "local-development-finding-fingerprint-pepper-change-me",
        }
        if any(
            value in forbidden_values
            or len(value) < 32
            or "change-me" in value.lower()
            or "replace-with" in value.lower()
            for value in application_secrets
        ):
            raise ValueError("Production requires independent secrets of at least 32 characters")

        infrastructure_secrets = [
            credential_from_url(self.database_url, "database"),
            credential_from_url(self.redis_url, "Redis"),
        ]
        all_secrets = application_secrets + infrastructure_secrets
        if len(set(all_secrets)) != len(all_secrets):
            raise ValueError("Production security and infrastructure secrets must be independent")
        if self.api_docs_enabled:
            raise ValueError("Production API documentation must be disabled")
        if not self.allowed_hosts or any(
            not host.strip() or "*" in host for host in self.allowed_hosts
        ):
            raise ValueError("Production requires an explicit allowed-host list")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
