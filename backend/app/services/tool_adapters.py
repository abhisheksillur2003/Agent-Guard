from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, cast
from uuid import UUID

from backend.app.core.errors import ValidationError

SENSITIVE_KEY_PARTS = ("password", "secret", "token", "credential", "api_key", "apikey")


@dataclass(frozen=True)
class AdapterExecutionContext:
    execution_id: UUID
    decision_id: UUID
    idempotency_key: str
    operation: str
    environment: str


class ToolAdapter(Protocol):
    name: str
    version: str
    retry_safe: bool

    async def execute(
        self,
        arguments: dict[str, Any],
        context: AdapterExecutionContext,
    ) -> dict[str, Any]: ...


class SafeEchoAdapter:
    name = "safe_echo"
    version = "1"
    retry_safe = True

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


ADAPTERS: dict[tuple[str, str], ToolAdapter] = {
    (SafeEchoAdapter.name, SafeEchoAdapter.version): SafeEchoAdapter(),
}


def get_adapter(name: str, version: str) -> ToolAdapter:
    adapter = ADAPTERS.get((name, version))
    if adapter is None:
        raise ValidationError("The configured tool adapter is not registered")
    return adapter


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
