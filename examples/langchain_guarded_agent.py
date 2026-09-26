from __future__ import annotations

import asyncio

from agentguard_sdk import AgentGuardError
from agentguard_sdk.integrations import FrameworkToolOutput
from agentguard_sdk.integrations.langchain import create_langchain_tool
from examples.framework_agent_common import (
    RefundArguments,
    framework_config,
    parse_framework_args,
    planned_action,
    report_failure,
    report_output,
)


async def run() -> int:
    args = parse_framework_args("LangChain")
    try:
        config = framework_config(args)
        action = await planned_action(args)
        tool = create_langchain_tool(config=config, args_schema=RefundArguments)
        raw_output = await tool.ainvoke(action.arguments)
        output = FrameworkToolOutput.model_validate(raw_output)
        return report_output(output)
    except (AgentGuardError, RuntimeError, ValueError) as exc:
        return report_failure(exc)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
