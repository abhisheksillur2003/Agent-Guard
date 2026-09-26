from __future__ import annotations

import json
from typing import Any, TypeVar, cast
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

import httpx
from pydantic import BaseModel, SecretStr

from agentguard_sdk.errors import (
    AgentGuardAPIError,
    AgentGuardConfigurationError,
    AgentGuardProtocolError,
    AgentGuardUnavailableError,
)
from agentguard_sdk.models import (
    Decision,
    DecisionOutcome,
    Execution,
    GuardedResult,
    GuardedResultStatus,
    ToolRequest,
)

ModelT = TypeVar("ModelT", bound=BaseModel)
LOCAL_HTTP_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _api_base_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise AgentGuardConfigurationError("AgentGuard API URL is invalid") from exc
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
        raise AgentGuardConfigurationError(
            "AgentGuard API URL requires HTTP(S), a host, and no credentials, query, or fragment"
        )
    if parsed.scheme != "https" and parsed.hostname not in LOCAL_HTTP_HOSTS:
        raise AgentGuardConfigurationError(
            "Remote AgentGuard API URLs must use HTTPS to protect the agent credential"
        )
    path = parsed.path.rstrip("/")
    if not path.endswith("/api/v1"):
        path = f"{path}/api/v1"
    return urlunsplit((parsed.scheme, parsed.netloc, f"{path}/", "", ""))


class AgentGuardClient:
    """Asynchronous, fail-closed client for AgentGuard's agent API."""

    def __init__(
        self,
        *,
        base_url: str,
        agent_token: str,
        timeout_seconds: float = 15.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if len(agent_token) < 8:
            raise AgentGuardConfigurationError("Agent credential is missing or invalid")
        if not 0 < timeout_seconds <= 300:
            raise AgentGuardConfigurationError("Timeout must be between 0 and 300 seconds")
        self._agent_token = SecretStr(agent_token)
        self._client = httpx.AsyncClient(
            base_url=_api_base_url(base_url),
            headers={
                "Authorization": f"Bearer {self._agent_token.get_secret_value()}",
                "Accept": "application/json",
                "User-Agent": "AgentGuard-Python-SDK/0.12.0",
            },
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )

    async def __aenter__(self) -> AgentGuardClient:
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def evaluate(self, request: ToolRequest) -> Decision:
        return await self._post("tool-requests/evaluate", request.model_dump(mode="json"), Decision)

    async def execute(
        self,
        *,
        decision_id: UUID,
        arguments: dict[str, Any],
    ) -> Execution:
        try:
            json.dumps(arguments, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise AgentGuardConfigurationError(
                "Execution arguments must contain finite JSON values"
            ) from exc
        return await self._post(
            "executions",
            {"decision_id": str(decision_id), "arguments": arguments},
            Execution,
        )

    async def guarded_execute(self, request: ToolRequest) -> GuardedResult:
        decision = await self.evaluate(request)
        if decision.outcome == DecisionOutcome.DENY:
            return GuardedResult(status=GuardedResultStatus.DENIED, decision=decision)
        if decision.outcome == DecisionOutcome.REQUIRE_APPROVAL:
            return GuardedResult(
                status=GuardedResultStatus.APPROVAL_REQUIRED,
                decision=decision,
            )
        execution = await self.execute(
            decision_id=decision.id,
            arguments=request.arguments,
        )
        return GuardedResult(
            status=GuardedResultStatus.EXECUTED,
            decision=decision,
            execution=execution,
        )

    async def _post(
        self,
        path: str,
        payload: dict[str, Any],
        response_model: type[ModelT],
    ) -> ModelT:
        try:
            response = await self._client.post(path, json=payload)
        except httpx.RequestError as exc:
            raise AgentGuardUnavailableError(
                "AgentGuard is unavailable; the tool action was not authorized"
            ) from exc
        if not response.is_success:
            raise self._api_error(response)
        try:
            return response_model.model_validate(response.json())
        except ValueError as exc:
            raise AgentGuardProtocolError(
                "AgentGuard returned an invalid response; the tool action was stopped"
            ) from exc

    @staticmethod
    def _api_error(response: httpx.Response) -> AgentGuardAPIError:
        code = "HTTP_ERROR"
        message = "AgentGuard rejected the request"
        try:
            raw_body: object = response.json()
            body = cast(dict[str, object], raw_body) if isinstance(raw_body, dict) else {}
            raw_error = body.get("error")
            if isinstance(raw_error, dict):
                error = cast(dict[str, object], raw_error)
                if isinstance(error.get("code"), str):
                    code = cast(str, error["code"])[:120]
                if isinstance(error.get("message"), str):
                    message = cast(str, error["message"])[:500]
        except ValueError:
            pass
        return AgentGuardAPIError(
            status_code=response.status_code,
            code=code,
            message=message,
            request_id=response.headers.get("x-request-id"),
        )
