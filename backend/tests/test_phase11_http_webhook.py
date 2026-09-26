import hashlib
import ipaddress
import json
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import ValidationError as PydanticValidationError

from backend.app.core.config import Settings
from backend.app.services.tool_adapters import (
    ADAPTERS,
    AdapterExecutionContext,
    AdapterExecutionError,
    HttpWebhookAdapter,
    IPAddress,
)
from backend.tests.conftest import ApiContext
from backend.tests.test_phase3_api import provision_gateway
from backend.tests.test_phase10_production_config import production_settings

TARGET_URL = "https://hooks.example.com/agentguard"
PUBLIC_ADDRESS = ipaddress.IPv4Address("93.184.216.34")
BEARER_TOKEN = "webhook-bearer-token-with-more-than-32-characters"


def connector_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "http_webhook_enabled": True,
        "http_webhook_allowed_urls": [TARGET_URL],
        "http_webhook_bearer_tokens": {TARGET_URL: BEARER_TOKEN},
    }
    values.update(overrides)
    return Settings(**values)  # pyright: ignore[reportArgumentType]


async def public_resolver(_host: str, _port: int) -> set[IPAddress]:
    return {PUBLIC_ADDRESS}


def execution_context() -> AdapterExecutionContext:
    return AdapterExecutionContext(
        execution_id=uuid4(),
        decision_id=uuid4(),
        idempotency_key="stable-execution-key",
        operation="notify",
        environment="production",
    )


async def expect_adapter_error(
    adapter: HttpWebhookAdapter,
    arguments: dict[str, Any],
    code: str,
) -> None:
    with pytest.raises(AdapterExecutionError) as raised:
        await adapter.execute(arguments, execution_context())
    assert raised.value.code == code


def test_webhook_configuration_rejects_unsafe_values() -> None:
    with pytest.raises(PydanticValidationError, match="explicit URL allowlist"):
        Settings(http_webhook_enabled=True)
    with pytest.raises(PydanticValidationError, match="must reference allowlisted"):
        connector_settings(
            http_webhook_bearer_tokens={"https://other.example.com/hook": BEARER_TOKEN}
        )
    with pytest.raises(PydanticValidationError, match="no credentials, query, or fragment"):
        connector_settings(
            http_webhook_allowed_urls=[f"{TARGET_URL}?token=unsafe"],
            http_webhook_bearer_tokens={},
        )


def test_production_webhook_requires_https_and_strong_runtime_tokens() -> None:
    with pytest.raises(PydanticValidationError, match="must use HTTPS"):
        production_settings(
            http_webhook_enabled=True,
            http_webhook_allowed_urls=["http://hooks.example.com/agentguard"],
        )
    with pytest.raises(PydanticValidationError, match="at least 32"):
        production_settings(
            http_webhook_enabled=True,
            http_webhook_allowed_urls=[TARGET_URL],
            http_webhook_bearer_tokens={TARGET_URL: "short"},
        )

    settings = production_settings(
        http_webhook_enabled=True,
        http_webhook_allowed_urls=[TARGET_URL],
        http_webhook_bearer_tokens={TARGET_URL: BEARER_TOKEN},
    )
    assert settings.http_webhook_enabled is True


async def test_webhook_posts_once_without_persisting_response_content() -> None:
    captured: list[httpx.Request] = []
    response_content = b'{"customer_secret":"never-store-this"}'

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            202,
            content=response_content,
            headers={"content-type": "application/json; charset=utf-8"},
        )

    adapter = HttpWebhookAdapter(
        settings_factory=connector_settings,
        resolver=public_resolver,
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    context = execution_context()
    result = await adapter.execute(
        {"url": TARGET_URL, "payload": {"order_id": "ORD-123"}},
        context,
    )

    assert len(captured) == 1
    assert json.loads(captured[0].content) == {"order_id": "ORD-123"}
    assert captured[0].url.host == str(PUBLIC_ADDRESS)
    assert captured[0].headers["host"] == "hooks.example.com"
    assert captured[0].headers["authorization"] == f"Bearer {BEARER_TOKEN}"
    assert captured[0].headers["idempotency-key"] == context.idempotency_key
    assert result == {
        "accepted": True,
        "status_code": 202,
        "content_type": "application/json",
        "response_bytes": len(response_content),
        "response_sha256": hashlib.sha256(response_content).hexdigest(),
    }
    assert "never-store-this" not in json.dumps(result)


async def test_webhook_fails_closed_for_disabled_unlisted_and_private_targets() -> None:
    disabled = HttpWebhookAdapter(settings_factory=lambda: Settings())
    await expect_adapter_error(
        disabled,
        {"url": TARGET_URL, "payload": {}},
        "HTTP_WEBHOOK_DISABLED",
    )

    configured = HttpWebhookAdapter(
        settings_factory=connector_settings,
        resolver=public_resolver,
    )
    await expect_adapter_error(
        configured,
        {"url": "https://unlisted.example.com/hook", "payload": {}},
        "HTTP_WEBHOOK_URL_NOT_ALLOWED",
    )

    async def private_resolver(_host: str, _port: int) -> set[IPAddress]:
        return {ipaddress.IPv4Address("127.0.0.1")}

    private = HttpWebhookAdapter(
        settings_factory=connector_settings,
        resolver=private_resolver,
    )
    await expect_adapter_error(
        private,
        {"url": TARGET_URL, "payload": {}},
        "HTTP_WEBHOOK_PRIVATE_NETWORK_DENIED",
    )


@pytest.mark.parametrize(
    ("status", "content", "max_bytes", "expected_code"),
    [
        (302, b"", 65_536, "HTTP_WEBHOOK_UPSTREAM_REJECTED"),
        (200, b"too large", 3, "HTTP_WEBHOOK_RESPONSE_TOO_LARGE"),
    ],
)
async def test_webhook_rejects_redirects_and_oversized_responses(
    status: int,
    content: bytes,
    max_bytes: int,
    expected_code: str,
) -> None:
    async def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=content, headers={"location": TARGET_URL})

    adapter = HttpWebhookAdapter(
        settings_factory=lambda: connector_settings(http_webhook_max_response_bytes=max_bytes),
        resolver=public_resolver,
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    await expect_adapter_error(
        adapter,
        {"url": TARGET_URL, "payload": {}},
        expected_code,
    )


async def test_adapter_registry_and_required_capabilities(api_context: ApiContext) -> None:
    response = await api_context.client.get(
        "/api/v1/tools/adapters",
        headers=api_context.admin_headers,
    )
    assert response.status_code == 200
    webhook = next(item for item in response.json() if item["name"] == "http_webhook")
    assert webhook == {
        "name": "http_webhook",
        "version": "1",
        "retry_safe": False,
        "required_capabilities": ["external_egress", "write"],
        "configured": False,
    }

    base_tool = {
        "name": "phase11-webhook",
        "input_schema": {"type": "object"},
        "risk_class": "high",
        "adapter_name": "http_webhook",
        "adapter_version": "1",
    }
    missing = await api_context.client.post(
        "/api/v1/tools",
        headers=api_context.admin_headers,
        json={**base_tool, "capability_flags": ["write"]},
    )
    assert missing.status_code == 422
    assert "external_egress" in missing.json()["error"]["message"]

    registered = await api_context.client.post(
        "/api/v1/tools",
        headers=api_context.admin_headers,
        json={**base_tool, "capability_flags": ["write", "external_egress"]},
    )
    assert registered.status_code == 201


async def test_webhook_executes_through_guarded_decision_path(
    api_context: ApiContext,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(204)

    adapter = HttpWebhookAdapter(
        settings_factory=connector_settings,
        resolver=public_resolver,
        client_factory=lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    monkeypatch.setitem(ADAPTERS, (adapter.name, adapter.version), adapter)
    gateway = await provision_gateway(api_context, suffix="http-webhook")
    configured = await api_context.client.patch(
        f"/api/v1/tools/{gateway.tool_id}",
        headers=api_context.admin_headers,
        json={
            "input_schema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "const": TARGET_URL},
                    "payload": {"type": "object"},
                },
                "required": ["url", "payload"],
                "additionalProperties": False,
            },
            "capability_flags": ["write", "external_egress"],
            "adapter_name": adapter.name,
            "adapter_version": adapter.version,
        },
    )
    assert configured.status_code == 200

    arguments = {"url": TARGET_URL, "payload": {"order_id": "ORD-123"}}
    decision = await api_context.client.post(
        "/api/v1/tool-requests/evaluate",
        headers=gateway.agent_headers,
        json={
            "tool_id": str(gateway.tool_id),
            "operation": "refund",
            "environment": "production",
            "arguments": arguments,
            "idempotency_key": "phase11-webhook-001",
        },
    )
    assert decision.status_code == 200
    assert decision.json()["outcome"] == "allow"

    executed = await api_context.client.post(
        "/api/v1/executions",
        headers=gateway.agent_headers,
        json={"decision_id": decision.json()["id"], "arguments": arguments},
    )
    assert executed.status_code == 200
    assert executed.json()["status"] == "succeeded"
    assert executed.json()["adapter_name"] == "http_webhook"
    assert len(captured) == 1
    assert captured[0].headers["x-agentguard-execution-id"] == executed.json()["id"]
    assert UUID(captured[0].headers["x-agentguard-decision-id"]) == UUID(decision.json()["id"])
