from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.observability import record_approval_transition
from backend.app.models import (
    ActorType,
    ApprovalRequest,
    ApprovalStatus,
    ExecutionEvent,
    ExecutionStatus,
    ToolExecution,
)
from backend.app.services.audit import record_audit


async def expire_due_approvals(session: AsyncSession) -> int:
    now = datetime.now(UTC)
    approvals = list(
        (
            await session.scalars(
                select(ApprovalRequest)
                .where(
                    ApprovalRequest.status == ApprovalStatus.PENDING,
                    ApprovalRequest.expires_at <= now,
                )
                .with_for_update(skip_locked=True)
            )
        ).all()
    )
    for approval in approvals:
        approval.status = ApprovalStatus.EXPIRED
        approval.decided_at = now
        approval.decision_reason = "Approval window expired"
        record_audit(
            session,
            organization_id=approval.organization_id,
            actor_type=ActorType.SYSTEM,
            actor_id=None,
            action="approval.expire",
            target_type="approval_request",
            target_id=approval.id,
            before={"status": ApprovalStatus.PENDING},
            after={"status": ApprovalStatus.EXPIRED},
        )
    if approvals:
        await session.commit()
        record_approval_transition(ApprovalStatus.EXPIRED, len(approvals))
    return len(approvals)


async def reconcile_stale_executions(session: AsyncSession, stale_after_seconds: int) -> int:
    now = datetime.now(UTC)
    cutoff = now - timedelta(seconds=stale_after_seconds)
    executions = list(
        (
            await session.scalars(
                select(ToolExecution)
                .where(
                    ToolExecution.status == ExecutionStatus.RUNNING,
                    ToolExecution.started_at <= cutoff,
                )
                .with_for_update(skip_locked=True)
            )
        ).all()
    )
    for execution in executions:
        execution.status = ExecutionStatus.FAILED
        execution.error_code = "EXECUTION_WORKER_LOST"
        execution.completed_at = now
        session.add(
            ExecutionEvent(
                execution_id=execution.id,
                sequence=execution.attempt_count * 2 + 1,
                event_type="execution.reconciled",
                status=ExecutionStatus.FAILED,
                details_json={"error_code": execution.error_code},
            )
        )
        record_audit(
            session,
            organization_id=execution.organization_id,
            actor_type=ActorType.SYSTEM,
            actor_id=None,
            action="execution.reconcile",
            target_type="tool_execution",
            target_id=execution.id,
            before={"status": ExecutionStatus.RUNNING},
            after={"status": ExecutionStatus.FAILED, "error_code": execution.error_code},
        )
    if executions:
        await session.commit()
    return len(executions)
