from __future__ import annotations

from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel

from agentguard_sdk.integrations.common import (
    FrameworkToolConfig,
    FrameworkToolOutput,
    GuardedToolRunner,
)


def create_langchain_tool(
    *,
    config: FrameworkToolConfig,
    args_schema: type[BaseModel],
    runner: GuardedToolRunner | None = None,
) -> StructuredTool:
    if runner is not None and (runner.config != config or runner.namespace != "langchain"):
        raise ValueError("LangChain runner configuration does not match the tool configuration")
    guarded_runner = runner or GuardedToolRunner(config, namespace="langchain")

    def run_tool(**arguments: Any) -> FrameworkToolOutput:
        return guarded_runner.run(arguments)

    async def run_tool_async(**arguments: Any) -> FrameworkToolOutput:
        return await guarded_runner.arun(arguments)

    return StructuredTool.from_function(
        func=run_tool,
        coroutine=run_tool_async,
        name=config.name,
        description=config.description,
        args_schema=args_schema,
        infer_schema=False,
    )
