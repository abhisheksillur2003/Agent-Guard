from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import Agent, ExecutionStatus, PolicyDecision, ToolExecution
from backend.app.schemas.reliability import ReliabilityBudget
from backend.app.services.audit import snapshot_hash


@dataclass(frozen=True)
class ReliabilityEvaluation:
    allowed: bool
    reason_code: str | None
    evidence: dict[str, Any]


def parse_reliability_budget(agent: Agent) -> ReliabilityBudget:
    return ReliabilityBudget.model_validate(agent.budget_config)


def reliability_profile_hash(profile: ReliabilityBudget) -> str:
    hashed = snapshot_hash(profile.model_dump(mode="json"))
    if hashed is None:  # pragma: no cover - a profile is never None
        raise RuntimeError("Reliability profile could not be hashed")
    return hashed


async def acquire_agent_evaluation_lock(session: AsyncSession, agent_id: Any) -> None:
    """Serialize an agent's decision counters for the current transaction."""

    lock_key = agent_id.int & ((1 << 63) - 1)
    await session.execute(select(func.pg_advisory_xact_lock(lock_key)))


async def evaluate_reliability(
    session: AsyncSession,
    *,
    agent: Agent,
    request_hash: str,
    evaluated_at: datetime,
) -> ReliabilityEvaluation:
    try:
        profile = parse_reliability_budget(agent)
    except PydanticValidationError:
        return ReliabilityEvaluation(
            allowed=False,
            reason_code="RELIABILITY_CONFIGURATION_INVALID",
            evidence={"configuration_valid": False},
        )

    minute_start = evaluated_at - timedelta(minutes=1)
    loop_start = evaluated_at - timedelta(seconds=profile.loop_detection_window_seconds)
    day_start = evaluated_at.replace(hour=0, minute=0, second=0, microsecond=0)

    decisions_last_minute = int(
        await session.scalar(
            select(func.count())
            .select_from(PolicyDecision)
            .where(
                PolicyDecision.organization_id == agent.organization_id,
                PolicyDecision.agent_id == agent.id,
                PolicyDecision.created_at >= minute_start,
            )
        )
        or 0
    )
    identical_requests = int(
        await session.scalar(
            select(func.count())
            .select_from(PolicyDecision)
            .where(
                PolicyDecision.organization_id == agent.organization_id,
                PolicyDecision.agent_id == agent.id,
                PolicyDecision.request_hash == request_hash,
                PolicyDecision.created_at >= loop_start,
            )
        )
        or 0
    )
    executions_today = int(
        await session.scalar(
            select(func.count())
            .select_from(ToolExecution)
            .where(
                ToolExecution.organization_id == agent.organization_id,
                ToolExecution.agent_id == agent.id,
                ToolExecution.created_at >= day_start,
                ToolExecution.status != ExecutionStatus.CANCELLED,
            )
        )
        or 0
    )
    evidence: dict[str, Any] = {
        "configuration_valid": True,
        "profile_hash": reliability_profile_hash(profile),
        "limits": profile.model_dump(mode="json"),
        "observed": {
            "decisions_last_minute": decisions_last_minute,
            "identical_requests_in_window": identical_requests,
            "executions_today": executions_today,
        },
    }
    if decisions_last_minute >= profile.max_decisions_per_minute:
        return ReliabilityEvaluation(False, "RATE_LIMIT_EXCEEDED", evidence)
    if identical_requests >= profile.max_identical_requests_in_window:
        return ReliabilityEvaluation(False, "REQUEST_LOOP_DETECTED", evidence)
    if executions_today >= profile.max_executions_per_day:
        return ReliabilityEvaluation(False, "DAILY_EXECUTION_BUDGET_EXCEEDED", evidence)
    return ReliabilityEvaluation(True, None, evidence)
