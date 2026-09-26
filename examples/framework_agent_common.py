from __future__ import annotations

import argparse
import os
import sys
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from agentguard_sdk import AgentGuardError
from agentguard_sdk.integrations import FrameworkToolConfig, FrameworkToolOutput
from agentguard_sdk.models import GuardedResultStatus
from examples.ollama_guarded_agent import PlannedAction, plan_with_ollama


class RefundArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str = Field(min_length=1, description="Order identifier to refund")
    amount: float = Field(ge=0, description="Refund amount")
    region: str = Field(default="US", description="Order region")


def parse_framework_args(framework: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=f"Run an Ollama-planned tool action through AgentGuard and {framework}."
    )
    parser.add_argument("prompt", help="Natural-language request for Ollama")
    parser.add_argument("--tool-id", default=os.getenv("AGENTGUARD_TOOL_ID"))
    parser.add_argument("--run-id", default=os.getenv("AGENTGUARD_RUN_ID"))
    parser.add_argument(
        "--operation",
        default=os.getenv("AGENTGUARD_OPERATION", "refund"),
    )
    parser.add_argument(
        "--environment",
        default=os.getenv("AGENTGUARD_REQUESTED_ENVIRONMENT", "local"),
    )
    parser.add_argument(
        "--agentguard-url",
        default=os.getenv("AGENTGUARD_API_URL", "http://127.0.0.1:8000"),
    )
    parser.add_argument(
        "--ollama-url",
        default=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
    )
    parser.add_argument("--model", default=os.getenv("OLLAMA_MODEL", "llama3.2:3b"))
    args = parser.parse_args()
    if not args.tool_id or not args.run_id or not os.getenv("AGENTGUARD_AGENT_TOKEN"):
        parser.error(
            "set AGENTGUARD_AGENT_TOKEN, AGENTGUARD_TOOL_ID, and a stable AGENTGUARD_RUN_ID"
        )
    return args


def framework_config(args: argparse.Namespace) -> FrameworkToolConfig:
    token = os.environ["AGENTGUARD_AGENT_TOKEN"]
    return FrameworkToolConfig(
        name="guarded_refund",
        description="Request a refund through AgentGuard's deterministic control plane.",
        base_url=args.agentguard_url,
        agent_token=SecretStr(token),
        tool_id=UUID(args.tool_id),
        operation=args.operation,
        environment=args.environment,
        run_id=args.run_id,
    )


async def planned_action(args: argparse.Namespace) -> PlannedAction:
    action = await plan_with_ollama(
        prompt=args.prompt,
        base_url=args.ollama_url,
        model=args.model,
    )
    if action.operation.strip().lower() != args.operation.strip().lower():
        raise ValueError("Ollama selected an operation outside this tool wrapper")
    RefundArguments.model_validate(action.arguments)
    return action


def report_output(output: FrameworkToolOutput) -> int:
    print(output.model_dump_json(indent=2))
    if output.status == GuardedResultStatus.DENIED:
        return 3
    if output.status == GuardedResultStatus.APPROVAL_REQUIRED:
        return 4
    return 0 if output.execution_status == "succeeded" else 1


def report_failure(exc: AgentGuardError | RuntimeError | ValueError) -> int:
    print(f"Framework tool action stopped: {exc}", file=sys.stderr)
    return 1
