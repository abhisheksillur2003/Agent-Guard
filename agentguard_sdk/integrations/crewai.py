from __future__ import annotations

from typing import Any

from crewai.tools import BaseTool
from pydantic import BaseModel, PrivateAttr

from agentguard_sdk.integrations.common import (
    FrameworkToolConfig,
    FrameworkToolOutput,
    GuardedToolRunner,
)


class AgentGuardCrewAITool(BaseTool):
    _guarded_runner: GuardedToolRunner = PrivateAttr()

    def __init__(
        self,
        *,
        config: FrameworkToolConfig,
        args_schema: type[BaseModel],
        runner: GuardedToolRunner | None = None,
    ) -> None:
        if runner is not None and (runner.config != config or runner.namespace != "crewai"):
            raise ValueError("CrewAI runner configuration does not match the tool configuration")
        super().__init__(
            name=config.name,
            description=config.description,
            args_schema=args_schema,
            result_schema=FrameworkToolOutput,
        )
        self._guarded_runner = runner or GuardedToolRunner(config, namespace="crewai")

    def _run(self, **arguments: Any) -> FrameworkToolOutput:
        return self._guarded_runner.run(arguments)

    async def _arun(self, **arguments: Any) -> FrameworkToolOutput:
        return await self._guarded_runner.arun(arguments)


def create_crewai_tool(
    *,
    config: FrameworkToolConfig,
    args_schema: type[BaseModel],
    runner: GuardedToolRunner | None = None,
) -> AgentGuardCrewAITool:
    return AgentGuardCrewAITool(config=config, args_schema=args_schema, runner=runner)
