from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any
from uuid import UUID, uuid4

import httpx
from pydantic import BaseModel, ConfigDict, Field

from agentguard_sdk import AgentGuardClient, AgentGuardError, GuardedResultStatus, ToolRequest


class PlannedAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation: str = Field(min_length=1, max_length=120)
    arguments: dict[str, Any]


class OllamaGenerateResponse(BaseModel):
    response: str


async def plan_with_ollama(
    *,
    prompt: str,
    base_url: str,
    model: str,
) -> PlannedAction:
    instruction = (
        "Select one operation and its JSON arguments for the registered AgentGuard tool. "
        "Do not claim that the action is authorized; AgentGuard makes that decision.\n\n"
        f"User request: {prompt}"
    )
    try:
        async with httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(60),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = await client.post(
                "/api/generate",
                json={
                    "model": model,
                    "prompt": instruction,
                    "stream": False,
                    "format": PlannedAction.model_json_schema(),
                    "options": {"temperature": 0},
                },
            )
            response.raise_for_status()
            generated = OllamaGenerateResponse.model_validate(response.json())
            return PlannedAction.model_validate_json(generated.response)
    except (httpx.HTTPError, ValueError) as exc:
        raise RuntimeError("Ollama could not produce a valid tool request") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan a tool action with Ollama and execute it only through AgentGuard."
    )
    parser.add_argument("prompt", help="Natural-language task for the local model")
    parser.add_argument("--tool-id", default=os.getenv("AGENTGUARD_TOOL_ID"))
    parser.add_argument(
        "--agentguard-url",
        default=os.getenv("AGENTGUARD_API_URL", "http://127.0.0.1:8000"),
    )
    parser.add_argument(
        "--environment",
        default=os.getenv("AGENTGUARD_REQUESTED_ENVIRONMENT", "local"),
    )
    parser.add_argument(
        "--idempotency-key",
        default=f"ollama-agent-{uuid4()}",
        help="Persist and reuse this key when retrying the same logical request.",
    )
    parser.add_argument(
        "--ollama-url",
        default=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
    )
    parser.add_argument(
        "--model",
        default=os.getenv("OLLAMA_MODEL", "llama3.2:3b"),
    )
    return parser.parse_args()


async def run() -> int:
    args = parse_args()
    token = os.getenv("AGENTGUARD_AGENT_TOKEN")
    if not token or not args.tool_id:
        print(
            "Set AGENTGUARD_AGENT_TOKEN and AGENTGUARD_TOOL_ID before running the example.",
            file=sys.stderr,
        )
        return 2
    try:
        tool_id = UUID(args.tool_id)
        action = await plan_with_ollama(
            prompt=args.prompt,
            base_url=args.ollama_url,
            model=args.model,
        )
        request = ToolRequest(
            tool_id=tool_id,
            operation=action.operation,
            environment=args.environment,
            arguments=action.arguments,
            idempotency_key=args.idempotency_key,
        )
        async with AgentGuardClient(
            base_url=args.agentguard_url,
            agent_token=token,
        ) as client:
            result = await client.guarded_execute(request)
    except (AgentGuardError, RuntimeError, ValueError) as exc:
        print(f"Tool action stopped: {exc}", file=sys.stderr)
        return 1

    if result.status == GuardedResultStatus.DENIED:
        print(f"Denied by AgentGuard: {result.decision.reason_code}")
        return 3
    if result.status == GuardedResultStatus.APPROVAL_REQUIRED:
        print(
            "Approval required. Review the request in the AgentGuard dashboard, then execute "
            f"decision {result.decision.id} with the same arguments."
        )
        return 4
    assert result.execution is not None
    print(json.dumps(result.execution.result_summary, indent=2, sort_keys=True))
    return 0 if result.execution.status == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
