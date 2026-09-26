from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import socket
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any, Protocol, cast
from uuid import UUID

import httpx

from backend.app.core.config import Settings, get_settings
from backend.app.core.errors import ValidationError
from backend.app.models.enums import ToolCapability

SENSITIVE_KEY_PARTS = ("password", "secret", "token", "credential", "api_key", "apikey")
EMPTY_REQUIRED_CAPABILITIES: frozenset[ToolCapability] = frozenset()
IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
AddressResolver = Callable[[str, int], Awaitable[set[IPAddress]]]
ClientFactory = Callable[[], httpx.AsyncClient]
SettingsFactory = Callable[[], Settings]


@dataclass(frozen=True)
class AdapterExecutionContext:
    execution_id: UUID
    decision_id: UUID
    idempotency_key: str
    operation: str
    environment: str


@dataclass(frozen=True)
class AdapterMetadata:
    name: str
    version: str
    retry_safe: bool
    required_capabilities: tuple[ToolCapability, ...]
    configured: bool


class AdapterExecutionError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ToolAdapter(Protocol):
    name: str
    version: str
    retry_safe: bool
    required_capabilities: frozenset[ToolCapability]

    def is_configured(self) -> bool: ...

    async def execute(
        self,
        arguments: dict[str, Any],
        context: AdapterExecutionContext,
    ) -> dict[str, Any]: ...


class SafeEchoAdapter:
    name = "safe_echo"
    version = "1"
    retry_safe = True
    required_capabilities: frozenset[ToolCapability] = frozenset()

    def is_configured(self) -> bool:
        return True

    async def execute(
        self,
        arguments: dict[str, Any],
        context: AdapterExecutionContext,
    ) -> dict[str, Any]:
        return {
            "accepted": True,
            "argument_fields": sorted(arguments),
            "argument_count": len(arguments),
            "execution_id": str(context.execution_id),
        }


async def _resolve_addresses(host: str, port: int) -> set[IPAddress]:
    try:
        records = await asyncio.get_running_loop().getaddrinfo(
            host,
            port,
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise AdapterExecutionError("HTTP_WEBHOOK_DNS_FAILED") from exc
    addresses: set[IPAddress] = set()
    for record in records:
        addresses.add(ipaddress.ip_address(record[4][0]))
    if not addresses:
        raise AdapterExecutionError("HTTP_WEBHOOK_DNS_FAILED")
    return addresses


def _new_http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(10.0),
        follow_redirects=False,
        trust_env=False,
    )


def _normalized_webhook_url(value: str) -> tuple[str, httpx.URL]:
    try:
        url = httpx.URL(value)
    except (TypeError, ValueError) as exc:
        raise AdapterExecutionError("HTTP_WEBHOOK_ARGUMENTS_INVALID") from exc
    if (
        url.scheme not in {"http", "https"}
        or not url.host
        or url.userinfo
        or url.query
        or url.fragment
    ):
        raise AdapterExecutionError("HTTP_WEBHOOK_ARGUMENTS_INVALID")
    return str(url), url


class HttpWebhookAdapter:
    name = "http_webhook"
    version = "1"
    retry_safe = False
    required_capabilities = frozenset({ToolCapability.WRITE, ToolCapability.EXTERNAL_EGRESS})

    def __init__(
        self,
        *,
        settings_factory: SettingsFactory = get_settings,
        resolver: AddressResolver = _resolve_addresses,
        client_factory: ClientFactory = _new_http_client,
    ) -> None:
        self._settings_factory = settings_factory
        self._resolver = resolver
        self._client_factory = client_factory

    def is_configured(self) -> bool:
        settings = self._settings_factory()
        return settings.http_webhook_enabled and bool(settings.http_webhook_allowed_urls)

    async def execute(
        self,
        arguments: dict[str, Any],
        context: AdapterExecutionContext,
    ) -> dict[str, Any]:
        settings = self._settings_factory()
        if not settings.http_webhook_enabled:
            raise AdapterExecutionError("HTTP_WEBHOOK_DISABLED")
        if set(arguments) != {"url", "payload"} or not isinstance(arguments["url"], str):
            raise AdapterExecutionError("HTTP_WEBHOOK_ARGUMENTS_INVALID")
        try:
            json.dumps(arguments["payload"], allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise AdapterExecutionError("HTTP_WEBHOOK_ARGUMENTS_INVALID") from exc

        target, url = _normalized_webhook_url(arguments["url"])
        try:
            allowed_urls = {
                _normalized_webhook_url(item)[0] for item in settings.http_webhook_allowed_urls
            }
        except AdapterExecutionError as exc:
            raise AdapterExecutionError("HTTP_WEBHOOK_CONFIGURATION_INVALID") from exc
        if target not in allowed_urls:
            raise AdapterExecutionError("HTTP_WEBHOOK_URL_NOT_ALLOWED")
        if settings.environment == "production" and url.scheme != "https":
            raise AdapterExecutionError("HTTP_WEBHOOK_HTTPS_REQUIRED")

        port = url.port or (443 if url.scheme == "https" else 80)
        addresses = await self._resolver(url.host, port)
        if not settings.http_webhook_allow_private_networks and any(
            not address.is_global for address in addresses
        ):
            raise AdapterExecutionError("HTTP_WEBHOOK_PRIVATE_NETWORK_DENIED")
        selected_address = min(addresses, key=lambda item: (item.version, int(item)))
        connect_target = url.copy_with(host=str(selected_address))

        headers = {
            "User-Agent": f"AgentGuard/{settings.service_version}",
            "Host": url.netloc.decode("ascii"),
            "Idempotency-Key": context.idempotency_key,
            "X-AgentGuard-Execution-ID": str(context.execution_id),
            "X-AgentGuard-Decision-ID": str(context.decision_id),
        }
        normalized_tokens = {
            _normalized_webhook_url(item)[0]: token
            for item, token in settings.http_webhook_bearer_tokens.items()
        }
        bearer_token = normalized_tokens.get(target)
        if bearer_token is not None:
            headers["Authorization"] = f"Bearer {bearer_token.get_secret_value()}"

        digest = hashlib.sha256()
        response_bytes = 0
        try:
            async with (
                self._client_factory() as client,
                client.stream(
                    "POST",
                    connect_target,
                    json=arguments["payload"],
                    headers=headers,
                    extensions={"sni_hostname": url.host},
                ) as response,
            ):
                if not 200 <= response.status_code < 300:
                    raise AdapterExecutionError("HTTP_WEBHOOK_UPSTREAM_REJECTED")
                async for chunk in response.aiter_bytes():
                    response_bytes += len(chunk)
                    if response_bytes > settings.http_webhook_max_response_bytes:
                        raise AdapterExecutionError("HTTP_WEBHOOK_RESPONSE_TOO_LARGE")
                    digest.update(chunk)
                content_type = response.headers.get("content-type", "")
                return {
                    "accepted": True,
                    "status_code": response.status_code,
                    "content_type": content_type.split(";", 1)[0].lower()[:120],
                    "response_bytes": response_bytes,
                    "response_sha256": digest.hexdigest(),
                }
        except AdapterExecutionError:
            raise
        except httpx.RequestError as exc:
            raise AdapterExecutionError("HTTP_WEBHOOK_REQUEST_FAILED") from exc


ADAPTERS: dict[tuple[str, str], ToolAdapter] = {
    (SafeEchoAdapter.name, SafeEchoAdapter.version): SafeEchoAdapter(),
    (HttpWebhookAdapter.name, HttpWebhookAdapter.version): HttpWebhookAdapter(),
}


def get_adapter(name: str, version: str) -> ToolAdapter:
    adapter = ADAPTERS.get((name, version))
    if adapter is None:
        raise ValidationError("The configured tool adapter is not registered")
    return adapter


def adapter_metadata() -> list[AdapterMetadata]:
    return [
        AdapterMetadata(
            name=adapter.name,
            version=adapter.version,
            retry_safe=adapter.retry_safe,
            required_capabilities=tuple(sorted(adapter.required_capabilities, key=str)),
            configured=adapter.is_configured(),
        )
        for adapter in sorted(ADAPTERS.values(), key=lambda item: (item.name, item.version))
    ]


def validate_adapter_capabilities(
    adapter: ToolAdapter,
    capabilities: Iterable[ToolCapability | str],
) -> None:
    selected = {ToolCapability(item) for item in capabilities}
    required_value: object = getattr(adapter, "required_capabilities", None)
    required = (
        cast(frozenset[ToolCapability], required_value)
        if isinstance(required_value, frozenset)
        else EMPTY_REQUIRED_CAPABILITIES
    )
    missing = required.difference(selected)
    if missing:
        names = ", ".join(sorted(item.value for item in missing))
        raise ValidationError(f"The {adapter.name} adapter requires capabilities: {names}")


def sanitize_result(value: Any, *, key: str | None = None, depth: int = 0) -> Any:
    if key is not None and any(part in key.lower() for part in SENSITIVE_KEY_PARTS):
        return "[REDACTED]"
    if depth >= 5:
        return "[MAX_DEPTH]"
    if isinstance(value, dict):
        mapping = cast(dict[Any, Any], value)
        return {
            str(item_key)[:120]: sanitize_result(
                item_value,
                key=str(item_key),
                depth=depth + 1,
            )
            for item_key, item_value in list(mapping.items())[:100]
        }
    if isinstance(value, list):
        items = cast(list[Any], value)
        return [sanitize_result(item, depth=depth + 1) for item in items[:100]]
    if isinstance(value, str):
        return value[:500]
    if value is None or isinstance(value, bool | int | float):
        return value
    return str(value)[:500]
