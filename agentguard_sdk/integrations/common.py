from __future__ import annotations

import asyncio
import hashlib
import json
import re
from typing import Any
from uuid import UUID

import httpx
from pydantic import ConfigDict, Field, SecretStr, field_validator

from agentguard_sdk.client import AgentGuardClient
from agentguard_sdk.errors import AgentGuardError
from agentguard_sdk.models import (
    ExecutionStatus,
    GuardedResult,
    GuardedResultStatus,
    SDKModel,
    ToolRequest,
)


class FrameworkIntegrationError(AgentGuardError):
    """A framework tool stopped because AgentGuard did not authorize execution."""


class FrameworkToolConfig(SDKModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    description: str = Field(min_length=1, max_length=1000)
    base_url: str
    agent_token: SecretStr
    tool_id: UUID
    operation: str = Field(min_length=1, max_length=120)
    environment: str = Field(min_length=1, max_length=80)
    run_id: str = Field(min_length=8, max_length=200)
    timeout_seconds: float = Field(default=15.0, gt=0, le=300)

    @field_validator("operation", "environment")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        return value.strip().lower()


class FrameworkToolOutput(SDKModel):
    status: GuardedResultStatus
    reason_code: str
    decision_id: UUID
    execution_id: UUID | None = None
    execution_status: ExecutionStatus | None = None
    result_summary: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None


class GuardedToolRunner:
    def __init__(
        self,
        config: FrameworkToolConfig,
        *,
        namespace: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if re.fullmatch(r"[a-z][a-z0-9_-]{0,15}", namespace) is None:
            raise ValueError("Framework namespace must be a lowercase identifier")
        self.config = config
        self._namespace = namespace
        self._transport = transport

    @property
    def namespace(self) -> str:
        return self._namespace

    async def arun(self, arguments: dict[str, Any]) -> FrameworkToolOutput:
        request = ToolRequest(
            tool_id=self.config.tool_id,
            operation=self.config.operation,
            environment=self.config.environment,
            arguments=arguments,
            idempotency_key=self.idempotency_key_for(arguments),
        )
        try:
            async with AgentGuardClient(
                base_url=self.config.base_url,
                agent_token=self.config.agent_token.get_secret_value(),
                timeout_seconds=self.config.timeout_seconds,
                transport=self._transport,
            ) as client:
                result = await client.guarded_execute(request)
        except AgentGuardError as exc:
            raise self._stopped_error() from exc
        return self._output(result)

    async def resume_approved(
        self,
        *,
        decision_id: UUID,
        arguments: dict[str, Any],
    ) -> FrameworkToolOutput:
        try:
            async with AgentGuardClient(
                base_url=self.config.base_url,
                agent_token=self.config.agent_token.get_secret_value(),
                timeout_seconds=self.config.timeout_seconds,
                transport=self._transport,
            ) as client:
                execution = await client.execute(
                    decision_id=decision_id,
                    arguments=arguments,
                )
        except AgentGuardError as exc:
            raise self._stopped_error() from exc
        return FrameworkToolOutput(
            status=GuardedResultStatus.EXECUTED,
            reason_code="APPROVED_EXECUTION",
            decision_id=decision_id,
            execution_id=execution.id,
            execution_status=execution.status,
            result_summary=execution.result_summary,
            error_code=execution.error_code,
        )

    def run(self, arguments: dict[str, Any]) -> FrameworkToolOutput:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.arun(arguments))
        raise FrameworkIntegrationError(
            "Synchronous framework tool execution cannot run inside an active event loop; "
            "use the framework's asynchronous tool API"
        )

    def idempotency_key_for(self, arguments: dict[str, Any]) -> str:
        try:
            canonical_arguments = json.dumps(
                arguments,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        except (TypeError, ValueError) as exc:
            raise FrameworkIntegrationError("Framework tool arguments must be valid JSON") from exc
        identity = "\x00".join(
            (
                self._namespace,
                self.config.run_id,
                str(self.config.tool_id),
                self.config.operation,
                self.config.environment,
                canonical_arguments,
            )
        )
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        return f"{self._namespace}-{digest}"

    @staticmethod
    def _stopped_error() -> FrameworkIntegrationError:
        return FrameworkIntegrationError("AgentGuard did not authorize the framework tool action")

    @staticmethod
    def _output(result: GuardedResult) -> FrameworkToolOutput:
        execution = result.execution
        return FrameworkToolOutput(
            status=result.status,
            reason_code=result.decision.reason_code,
            decision_id=result.decision.id,
            execution_id=execution.id if execution else None,
            execution_status=execution.status if execution else None,
            result_summary=execution.result_summary if execution else {},
            error_code=execution.error_code if execution else None,
        )
