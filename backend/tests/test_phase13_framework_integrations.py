from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import httpx
import pytest
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from agentguard_sdk.integrations import (
    FrameworkIntegrationError,
    FrameworkToolConfig,
    FrameworkToolOutput,
    GuardedToolRunner,
)
from agentguard_sdk.integrations.crewai import create_crewai_tool
from agentguard_sdk.integrations.langchain import create_langchain_tool
from agentguard_sdk.models import ToolRequest
from backend.app.main import app
from backend.tests.conftest import ApiContext
from backend.tests.test_phase3_api import create_policy, provision_gateway
from backend.tests.test_phase12_sdk import decision_payload, execution_payload


class RefundArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str = Field(min_length=1)
    amount: float = Field(ge=0)
    region: str = "US"


def framework_config(**overrides: object) -> FrameworkToolConfig:
    values: dict[str, object] = {
        "name": "guarded_refund",
        "description": "Request a refund through the AgentGuard control plane.",
        "base_url": "https://agentguard.example.com",
        "agent_token": SecretStr("agk_framework-test-credential"),
        "tool_id": uuid4(),
        "operation": "refund",
        "environment": "production",
        "run_id": "framework-run-001",
    }
    values.update(overrides)
    return FrameworkToolConfig(**values)  # pyright: ignore[reportArgumentType]


def successful_transport(
    captured: list[httpx.Request],
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if request.url.path.endswith("/tool-requests/evaluate"):
            body = json.loads(request.content)
            tool_request = ToolRequest.model_validate(body)
            return httpx.Response(200, json=decision_payload(tool_request))
        decision_id = json.loads(captured[-2].content)["idempotency_key"]
        evaluation_request = ToolRequest.model_validate(json.loads(captured[-2].content))
        decision = decision_payload(evaluation_request)
        decision["id"] = json.loads(request.content)["decision_id"]
        assert decision_id == evaluation_request.idempotency_key
        return httpx.Response(200, json=execution_payload(decision))

    return httpx.MockTransport(handler)


async def test_langchain_tool_executes_only_through_guarded_runner() -> None:
    captured: list[httpx.Request] = []
    config = framework_config()
    runner = GuardedToolRunner(
        config,
        namespace="langchain",
        transport=successful_transport(captured),
    )
    tool = create_langchain_tool(config=config, args_schema=RefundArguments, runner=runner)

    output = await tool.ainvoke({"order_id": "ORD-123", "amount": 100, "region": "US"})

    assert isinstance(output, FrameworkToolOutput)
    assert output.status == "executed"
    assert output.execution_status == "succeeded"
    assert [request.url.path for request in captured] == [
        "/api/v1/tool-requests/evaluate",
        "/api/v1/executions",
    ]
    assert all(
        request.headers["authorization"] == "Bearer agk_framework-test-credential"
        for request in captured
    )


async def test_framework_idempotency_is_stable_per_run_and_arguments() -> None:
    captured: list[httpx.Request] = []
    config = framework_config()
    runner = GuardedToolRunner(
        config,
        namespace="langchain",
        transport=successful_transport(captured),
    )

    first = await runner.arun({"amount": 100, "order_id": "ORD-123"})
    second = await runner.arun({"order_id": "ORD-123", "amount": 100})

    assert first.status == second.status == "executed"
    evaluations = [
        json.loads(request.content)
        for request in captured
        if request.url.path.endswith("/tool-requests/evaluate")
    ]
    assert evaluations[0]["idempotency_key"] == evaluations[1]["idempotency_key"]

    other_run = GuardedToolRunner(
        config.model_copy(update={"run_id": "framework-run-002"}),
        namespace="langchain",
        transport=successful_transport([]),
    )
    assert runner.idempotency_key_for(evaluations[0]["arguments"]) != other_run.idempotency_key_for(
        evaluations[0]["arguments"]
    )


@pytest.mark.parametrize("outcome", ["deny", "require_approval"])
async def test_langchain_tool_does_not_execute_blocked_decisions(outcome: str) -> None:
    captured: list[httpx.Request] = []
    config = framework_config()

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        body = ToolRequest.model_validate(json.loads(request.content))
        return httpx.Response(200, json=decision_payload(body, outcome))

    runner = GuardedToolRunner(
        config,
        namespace="langchain",
        transport=httpx.MockTransport(handler),
    )
    tool = create_langchain_tool(config=config, args_schema=RefundArguments, runner=runner)

    output = await tool.ainvoke({"order_id": "ORD-123", "amount": 100})

    assert isinstance(output, FrameworkToolOutput)
    assert output.status == ("denied" if outcome == "deny" else "approval_required")
    assert output.execution_id is None
    assert len(captured) == 1


async def test_crewai_tool_uses_typed_async_execution() -> None:
    captured: list[httpx.Request] = []
    config = framework_config()
    runner = GuardedToolRunner(
        config,
        namespace="crewai",
        transport=successful_transport(captured),
    )
    tool = create_crewai_tool(config=config, args_schema=RefundArguments, runner=runner)

    output = await tool.arun(order_id="ORD-123", amount=100, region="US")

    assert isinstance(output, FrameworkToolOutput)
    assert output.status == "executed"
    assert output.execution_status == "succeeded"
    assert len(captured) == 2


@pytest.mark.parametrize("framework", ["langchain", "crewai"])
async def test_framework_tools_fail_closed_when_agentguard_is_unavailable(
    framework: str,
) -> None:
    config = framework_config()

    def unavailable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    runner = GuardedToolRunner(
        config,
        namespace=framework,
        transport=httpx.MockTransport(unavailable),
    )
    if framework == "langchain":
        tool: Any = create_langchain_tool(
            config=config,
            args_schema=RefundArguments,
            runner=runner,
        )
        invocation = tool.ainvoke({"order_id": "ORD-123", "amount": 100})
    else:
        tool = create_crewai_tool(config=config, args_schema=RefundArguments, runner=runner)
        invocation = tool.arun(order_id="ORD-123", amount=100)

    with pytest.raises(FrameworkIntegrationError, match="did not authorize"):
        await invocation


def test_framework_config_redacts_agent_credentials() -> None:
    config = framework_config()
    assert "agk_framework-test-credential" not in repr(config)
    assert config.agent_token.get_secret_value() == "agk_framework-test-credential"


async def test_both_frameworks_execute_through_real_api(api_context: ApiContext) -> None:
    gateway = await provision_gateway(api_context, suffix="phase13-frameworks")
    credential = gateway.agent_headers["Authorization"].removeprefix("Bearer ")
    common = {
        "base_url": "https://test",
        "agent_token": SecretStr(credential),
        "tool_id": gateway.tool_id,
    }
    arguments = {"order_id": "ORD-789", "amount": 100, "region": "US"}

    langchain_config = framework_config(**common, run_id="phase13-langchain-run")
    langchain_runner = GuardedToolRunner(
        langchain_config,
        namespace="langchain",
        transport=httpx.ASGITransport(app=app),
    )
    langchain_tool = create_langchain_tool(
        config=langchain_config,
        args_schema=RefundArguments,
        runner=langchain_runner,
    )
    langchain_output = await langchain_tool.ainvoke(arguments)

    crewai_config = framework_config(**common, run_id="phase13-crewai-run")
    crewai_runner = GuardedToolRunner(
        crewai_config,
        namespace="crewai",
        transport=httpx.ASGITransport(app=app),
    )
    crewai_tool = create_crewai_tool(
        config=crewai_config,
        args_schema=RefundArguments,
        runner=crewai_runner,
    )
    crewai_output = await crewai_tool.arun(**arguments)

    assert langchain_output.status == "executed"
    assert crewai_output.status == "executed"
    assert langchain_output.execution_id != crewai_output.execution_id


async def test_framework_runner_resumes_only_after_human_approval(
    api_context: ApiContext,
) -> None:
    gateway = await provision_gateway(api_context, suffix="phase13-approval")
    await create_policy(
        api_context,
        gateway,
        name="Phase 13 framework approval",
        effect="require_approval",
        reason_code="FRAMEWORK_HUMAN_REVIEW",
        conditions=[],
    )
    credential = gateway.agent_headers["Authorization"].removeprefix("Bearer ")
    config = framework_config(
        base_url="https://test",
        agent_token=SecretStr(credential),
        tool_id=gateway.tool_id,
        run_id="phase13-approval-run",
    )
    runner = GuardedToolRunner(
        config,
        namespace="langchain",
        transport=httpx.ASGITransport(app=app),
    )
    arguments = {"order_id": "ORD-APPROVE", "amount": 800, "region": "US"}

    stopped = await runner.arun(arguments)
    assert stopped.status == "approval_required"

    approvals = await api_context.client.get(
        "/api/v1/approvals",
        params={"decision_id": str(stopped.decision_id)},
        headers=api_context.admin_headers,
    )
    approval_id = approvals.json()[0]["id"]
    approved = await api_context.client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        json={"reason": "Approved framework action"},
        headers=api_context.admin_headers,
    )
    assert approved.status_code == 200

    resumed = await runner.resume_approved(
        decision_id=stopped.decision_id,
        arguments=arguments,
    )

    assert resumed.status == "executed"
    assert resumed.execution_status == "succeeded"
    assert resumed.reason_code == "APPROVED_EXECUTION"
