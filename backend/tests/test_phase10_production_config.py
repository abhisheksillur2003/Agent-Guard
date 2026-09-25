import httpx
import pytest
from pydantic import ValidationError

from backend.app.core.config import Settings
from backend.app.main import app


def production_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "production",
        "api_docs_enabled": False,
        "allowed_hosts": ["agentguard.example.com", "api"],
        "database_url": (
            "postgresql+asyncpg://agentguard:database-password-with-more-than-32-characters"
            "@postgres/agentguard"
        ),
        "redis_url": "redis://:redis-password-with-more-than-32-characters@redis:6379/0",
        "auth_signing_key": "auth-signing-key-with-more-than-32-characters",
        "agent_key_pepper": "agent-key-pepper-with-more-than-32-characters",
        "finding_fingerprint_pepper": "finding-pepper-with-more-than-32-characters",
    }
    values.update(overrides)
    return Settings(**values)  # pyright: ignore[reportArgumentType]


def test_valid_production_configuration_is_accepted() -> None:
    settings = production_settings()

    assert settings.environment == "production"
    assert settings.api_docs_enabled is False


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"api_docs_enabled": True}, "documentation"),
        ({"allowed_hosts": ["*"]}, "allowed-host"),
        ({"allowed_hosts": ["*.example.com"]}, "allowed-host"),
        ({"auth_signing_key": "short"}, "at least 32"),
        (
            {
                "agent_key_pepper": "auth-signing-key-with-more-than-32-characters",
            },
            "independent",
        ),
        (
            {
                "database_url": (
                    "postgresql+asyncpg://agentguard:replace-with-a-password@postgres/agentguard"
                )
            },
            "database password",
        ),
        ({"redis_url": "redis://redis:6379/0"}, "Redis password"),
    ],
)
def test_unsafe_production_configuration_is_rejected(
    override: dict[str, object], message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        production_settings(**override)


async def test_untrusted_host_is_rejected_before_routing() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://evil.example") as client:
        response = await client.get("/healthz")

    assert response.status_code == 400
