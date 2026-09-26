from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from jsonschema import Draft202012Validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import get_settings
from backend.app.core.errors import AuthorizationError, ConflictError, NotFoundError
from backend.app.core.observability import record_execution_attempt
from backend.app.models import (
    ActorType,
    Agent,
    AgentPermission,
    ApprovalRequest,
    ApprovalStatus,
    ExecutionEvent,
    ExecutionStatus,
    Policy,
    PolicyDecision,
    PolicyStatus,
    PolicyVersion,
    Tool,
    ToolExecution,
    ToolStatus,
)
from backend.app.services.approvals import get_approval
from backend.app.services.audit import record_audit
from backend.app.services.permissions import check_permission
from backend.app.services.policy_engine import canonical_hash
from backend.app.services.reliability import (
    parse_reliability_budget,
    reliability_profile_hash,
)
from backend.app.services.security_scanning import (
    active_detector_rows,
    detector_version_evidence,
)
from backend.app.services.tool_adapters import (
    AdapterExecutionContext,
    AdapterExecutionError,
    get_adapter,
    sanitize_result,
)


def _event(
    execution: ToolExecution,
    sequence: int,
    event_type: str,
    status: ExecutionStatus,
    details: dict[str, Any] | None = None,
) -> ExecutionEvent:
    return ExecutionEvent(
        execution_id=execution.id,
        sequence=sequence,
        event_type=event_type,
        status=status,
        details_json=details or {},
    )


async def _current_policy_versions(
    session: AsyncSession, organization_id: UUID
) -> list[dict[str, Any]]:
    rows = (
        await session.execute(
            select(Policy, PolicyVersion)
            .join(
                PolicyVersion,
                (PolicyVersion.policy_id == Policy.id)
                & (PolicyVersion.version == Policy.current_version),
            )
            .where(
                Policy.organization_id == organization_id,
                Policy.status == PolicyStatus.ACTIVE,
            )
            .order_by(Policy.priority, Policy.id)
        )
    ).all()
    return [
        {
            "policy_id": str(policy.id),
            "policy_version_id": str(version.id),
            "version": version.version,
        }
        for policy, version in rows
    ]


async def _validate_execution_authority(
    session: AsyncSession,
    *,
    agent: Agent,
    decision: PolicyDecision,
    arguments: dict[str, Any],
    request_id: str | None,
) -> tuple[Tool, ApprovalRequest | None]:
    settings = get_settings()
    if decision.created_at < datetime.now(UTC) - timedelta(
        minutes=settings.execution_decision_ttl_minutes
    ):
        raise AuthorizationError("Policy decision has expired; evaluate the request again")
    if decision.outcome == "deny":
        raise AuthorizationError("A denied tool request cannot be executed")
    if canonical_hash(arguments) != decision.arguments_hash:
        raise ConflictError("Execution arguments do not match the authorized request")

    tool = await session.scalar(
        select(Tool).where(
            Tool.id == decision.requested_tool_id,
            Tool.organization_id == agent.organization_id,
        )
    )
    if tool is None or tool.status != ToolStatus.ACTIVE:
        raise AuthorizationError("The authorized tool is unavailable")
    if tool.updated_at > decision.created_at:
        raise AuthorizationError("Tool configuration changed; evaluate the request again")
    validation_errors = list(  # pyright: ignore[reportUnknownVariableType]
        Draft202012Validator(tool.input_schema).iter_errors(  # pyright: ignore[reportUnknownMemberType]
            arguments
        )
    )
    if validation_errors:
        raise AuthorizationError("Tool arguments no longer satisfy the registered schema")

    permission = await check_permission(
        session,
        organization_id=agent.organization_id,
        agent_id=agent.id,
        tool_id=tool.id,
        operation=decision.operation,
        environment=decision.environment,
    )
    if not permission.allowed or permission.permission_id != decision.permission_id:
        raise AuthorizationError("Tool permission is no longer valid")
    permission_record = await session.get(AgentPermission, permission.permission_id)
    if permission_record is None or permission_record.updated_at > decision.created_at:
        raise AuthorizationError("Tool permission changed; evaluate the request again")

    evaluated_versions = decision.evidence_json.get("evaluated_policy_versions")
    if evaluated_versions != await _current_policy_versions(session, agent.organization_id):
        raise AuthorizationError("Policy configuration changed; evaluate the request again")
    evaluated_detectors = decision.evidence_json.get("evaluated_detector_versions")
    current_detectors = detector_version_evidence(
        await active_detector_rows(session, agent.organization_id)
    )
    if evaluated_detectors != current_detectors:
        raise AuthorizationError("Security detectors changed; evaluate the request again")
    try:
        current_reliability_hash = reliability_profile_hash(parse_reliability_budget(agent))
    except Exception as exc:
        raise AuthorizationError(
            "Reliability configuration is invalid; execution is denied"
        ) from exc
    evaluated_reliability = decision.evidence_json.get("reliability", {})
    if evaluated_reliability.get("profile_hash") != current_reliability_hash:
        raise AuthorizationError("Reliability limits changed; evaluate the request again")

    approval: ApprovalRequest | None = None
    if decision.outcome == "require_approval":
        approval = await session.scalar(
            select(ApprovalRequest).where(ApprovalRequest.decision_id == decision.id)
        )
        if approval is None:
            raise AuthorizationError("Required approval record is unavailable")
        approval = await get_approval(
            session,
            agent.organization_id,
            approval.id,
            request_id=request_id,
        )
        if approval.status != ApprovalStatus.APPROVED:
            raise AuthorizationError("Tool request has not been approved")
    return tool, approval


async def _run_execution_attempt(
    session: AsyncSession,
    *,
    execution: ToolExecution,
    decision: PolicyDecision,
    tool: Tool,
    arguments: dict[str, Any],
    request_id: str | None,
) -> ToolExecution:
    adapter = get_adapter(execution.adapter_name, execution.adapter_version)
    execution.attempt_count += 1
    execution.status = ExecutionStatus.RUNNING
    execution.started_at = datetime.now(UTC)
    execution.completed_at = None
    execution.error_code = None
    started_sequence = execution.attempt_count * 2
    session.add(
        _event(
            execution,
            started_sequence,
            "execution.started",
            ExecutionStatus.RUNNING,
            {"attempt": execution.attempt_count},
        )
    )
    await session.commit()

    try:
        raw_result = await asyncio.wait_for(
            adapter.execute(
                arguments,
                AdapterExecutionContext(
                    execution_id=execution.id,
                    decision_id=decision.id,
                    idempotency_key=str(execution.id),
                    operation=decision.operation,
                    environment=decision.environment,
                ),
            ),
            timeout=tool.execution_timeout_seconds,
        )
        sanitized = sanitize_result(raw_result)
        execution.result_summary = (
            sanitized if isinstance(sanitized, dict) else {"result": sanitized}
        )
        execution.status = ExecutionStatus.SUCCEEDED
        event_type = "execution.succeeded"
    except TimeoutError:
        execution.status = ExecutionStatus.TIMED_OUT
        execution.error_code = "EXECUTION_TIMEOUT"
        event_type = "execution.timed_out"
    except AdapterExecutionError as exc:
        execution.status = ExecutionStatus.FAILED
        execution.error_code = exc.code
        event_type = "execution.failed"
    except Exception:
        execution.status = ExecutionStatus.FAILED
        execution.error_code = "ADAPTER_EXECUTION_FAILED"
        event_type = "execution.failed"
    execution.completed_at = datetime.now(UTC)
    session.add(
        _event(
            execution,
            started_sequence + 1,
            event_type,
            execution.status,
            {
                "attempt": execution.attempt_count,
                **({"error_code": execution.error_code} if execution.error_code else {}),
            },
        )
    )
    record_audit(
        session,
        organization_id=execution.organization_id,
        actor_type=ActorType.AGENT,
        actor_id=execution.agent_id,
        action=event_type,
        target_type="tool_execution",
        target_id=execution.id,
        before={"status": ExecutionStatus.RUNNING, "attempt": execution.attempt_count},
        after={"status": execution.status, "error_code": execution.error_code},
        request_id=request_id,
    )
    await session.commit()
    await session.refresh(execution)
    record_execution_attempt(execution.status)
    return execution


async def execute_tool_request(
    session: AsyncSession,
    *,
    agent: Agent,
    decision_id: UUID,
    arguments: dict[str, Any],
    request_id: str | None,
) -> ToolExecution:
    decision = await session.scalar(
        select(PolicyDecision).where(
            PolicyDecision.id == decision_id,
            PolicyDecision.organization_id == agent.organization_id,
            PolicyDecision.agent_id == agent.id,
        )
    )
    if decision is None:
        raise NotFoundError("Policy decision")
    if canonical_hash(arguments) != decision.arguments_hash:
        raise ConflictError("Execution arguments do not match the authorized request")

    existing = await session.scalar(
        select(ToolExecution).where(ToolExecution.decision_id == decision.id)
    )
    if existing is not None:
        return existing

    tool, approval = await _validate_execution_authority(
        session,
        agent=agent,
        decision=decision,
        arguments=arguments,
        request_id=request_id,
    )
    get_adapter(tool.adapter_name, tool.adapter_version)
    profile = parse_reliability_budget(agent)
    execution = ToolExecution(
        organization_id=agent.organization_id,
        decision_id=decision.id,
        approval_id=approval.id if approval is not None else None,
        agent_id=agent.id,
        tool_id=tool.id,
        operation=decision.operation,
        environment=decision.environment,
        arguments_hash=decision.arguments_hash,
        status=ExecutionStatus.AUTHORIZED,
        adapter_name=tool.adapter_name,
        adapter_version=tool.adapter_version,
        max_attempts=profile.max_execution_attempts,
    )
    session.add(execution)
    try:
        await session.flush()
        session.add(
            _event(
                execution,
                1,
                "execution.authorized",
                ExecutionStatus.AUTHORIZED,
                {
                    "decision_id": str(decision.id),
                    "approval_id": str(execution.approval_id) if execution.approval_id else None,
                },
            )
        )
        record_audit(
            session,
            organization_id=agent.organization_id,
            actor_type=ActorType.AGENT,
            actor_id=agent.id,
            action="execution.authorize",
            target_type="tool_execution",
            target_id=execution.id,
            after={
                "decision_id": decision.id,
                "tool_id": tool.id,
                "status": ExecutionStatus.AUTHORIZED,
            },
            request_id=request_id,
        )
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await session.scalar(
            select(ToolExecution).where(ToolExecution.decision_id == decision.id)
        )
        if existing is not None:
            return existing
        raise
    await session.refresh(execution)

    return await _run_execution_attempt(
        session,
        execution=execution,
        decision=decision,
        tool=tool,
        arguments=arguments,
        request_id=request_id,
    )


async def retry_tool_execution(
    session: AsyncSession,
    *,
    agent: Agent,
    execution_id: UUID,
    arguments: dict[str, Any],
    request_id: str | None,
) -> ToolExecution:
    execution = await session.scalar(
        select(ToolExecution)
        .where(
            ToolExecution.id == execution_id,
            ToolExecution.organization_id == agent.organization_id,
            ToolExecution.agent_id == agent.id,
        )
        .with_for_update()
    )
    if execution is None:
        raise NotFoundError("Tool execution")
    if canonical_hash(arguments) != execution.arguments_hash:
        raise ConflictError("Retry arguments do not match the authorized request")
    if execution.status not in {ExecutionStatus.FAILED, ExecutionStatus.TIMED_OUT}:
        raise ConflictError("Only failed or timed-out executions can be retried")
    if execution.attempt_count >= execution.max_attempts:
        raise ConflictError("The execution retry limit has been reached")

    decision = await session.get(PolicyDecision, execution.decision_id)
    if decision is None:
        raise AuthorizationError("The execution's policy decision is unavailable")
    tool, _approval = await _validate_execution_authority(
        session,
        agent=agent,
        decision=decision,
        arguments=arguments,
        request_id=request_id,
    )
    if (
        tool.adapter_name != execution.adapter_name
        or tool.adapter_version != execution.adapter_version
    ):
        raise AuthorizationError("Tool adapter changed; evaluate the request again")
    adapter = get_adapter(execution.adapter_name, execution.adapter_version)
    if not getattr(adapter, "retry_safe", False):
        raise AuthorizationError("The configured adapter does not support idempotent retries")

    profile = parse_reliability_budget(agent)
    if execution.completed_at is not None:
        retry_after = execution.completed_at + timedelta(seconds=profile.retry_backoff_seconds)
        if datetime.now(UTC) < retry_after:
            raise ConflictError("The retry backoff period has not elapsed")

    record_audit(
        session,
        organization_id=agent.organization_id,
        actor_type=ActorType.AGENT,
        actor_id=agent.id,
        action="execution.retry",
        target_type="tool_execution",
        target_id=execution.id,
        before={"status": execution.status, "attempt": execution.attempt_count},
        after={"next_attempt": execution.attempt_count + 1},
        request_id=request_id,
    )
    return await _run_execution_attempt(
        session,
        execution=execution,
        decision=decision,
        tool=tool,
        arguments=arguments,
        request_id=request_id,
    )


async def list_executions(
    session: AsyncSession, organization_id: UUID, limit: int
) -> list[ToolExecution]:
    result = await session.scalars(
        select(ToolExecution)
        .where(ToolExecution.organization_id == organization_id)
        .order_by(ToolExecution.created_at.desc())
        .limit(limit)
    )
    return list(result.all())


async def get_execution(
    session: AsyncSession, organization_id: UUID, execution_id: UUID
) -> ToolExecution:
    execution = await session.scalar(
        select(ToolExecution).where(
            ToolExecution.id == execution_id,
            ToolExecution.organization_id == organization_id,
        )
    )
    if execution is None:
        raise NotFoundError("Tool execution")
    return execution


async def list_execution_events(
    session: AsyncSession, organization_id: UUID, execution_id: UUID
) -> list[ExecutionEvent]:
    await get_execution(session, organization_id, execution_id)
    result = await session.scalars(
        select(ExecutionEvent)
        .where(ExecutionEvent.execution_id == execution_id)
        .order_by(ExecutionEvent.sequence)
    )
    return list(result.all())
