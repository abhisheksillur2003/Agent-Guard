from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, cast
from uuid import UUID

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import get_settings
from backend.app.core.errors import ConflictError, NotFoundError
from backend.app.models import (
    ActorType,
    Agent,
    ApprovalRequest,
    ApprovalStatus,
    DecisionOutcome,
    Policy,
    PolicyDecision,
    PolicyEffect,
    PolicyStatus,
    PolicyVersion,
    SecurityFinding,
    Tool,
)
from backend.app.schemas.decisions import ToolRequestEvaluation
from backend.app.schemas.policies import (
    FieldMissingCondition,
    NumberGreaterThanCondition,
    PolicyCondition,
    PolicyDocument,
    ValueInCondition,
)
from backend.app.services.audit import record_audit
from backend.app.services.permissions import check_permission
from backend.app.services.reliability import (
    acquire_agent_evaluation_lock,
    evaluate_reliability,
)
from backend.app.services.security_scanning import (
    DetectedFinding,
    evaluate_security_detectors,
)

MISSING = object()


def canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def request_hash(data: ToolRequestEvaluation) -> str:
    return canonical_hash(
        {
            "tool_id": str(data.tool_id),
            "operation": data.operation,
            "environment": data.environment,
            "arguments": data.arguments,
        }
    )


def _argument_value(arguments: dict[str, Any], path: str) -> Any:
    current: Any = arguments
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return MISSING
        current = cast(dict[str, Any], current)[part]
    return current


def _same_json_value(left: Any, right: Any) -> bool:
    return json.dumps(left, sort_keys=True, separators=(",", ":")) == json.dumps(
        right, sort_keys=True, separators=(",", ":")
    )


def condition_matches(
    condition: PolicyCondition,
    arguments: dict[str, Any],
    evaluated_at: datetime,
) -> bool:
    if isinstance(condition, FieldMissingCondition):
        return _argument_value(arguments, condition.path) is MISSING
    if isinstance(condition, NumberGreaterThanCondition):
        value = _argument_value(arguments, condition.path)
        if value is MISSING or isinstance(value, bool):
            return False
        try:
            return Decimal(str(value)) > Decimal(str(condition.value))
        except (InvalidOperation, ValueError):
            return False
    if isinstance(condition, ValueInCondition):
        value = _argument_value(arguments, condition.path)
        return value is not MISSING and any(
            _same_json_value(value, blocked) for blocked in condition.values
        )
    hour = evaluated_at.astimezone(UTC).hour
    if condition.start_hour < condition.end_hour:
        inside = condition.start_hour <= hour < condition.end_hour
    else:
        inside = hour >= condition.start_hour or hour < condition.end_hour
    return not inside


def scope_matches(
    document: PolicyDocument,
    *,
    agent_id: UUID,
    tool_id: UUID,
    operation: str,
    environment: str,
) -> bool:
    scope = document.scope
    return (
        (not scope.agent_ids or agent_id in scope.agent_ids)
        and (not scope.tool_ids or tool_id in scope.tool_ids)
        and (not scope.operations or operation in scope.operations)
        and (not scope.environments or environment in scope.environments)
    )


async def _store_decision(
    session: AsyncSession,
    *,
    organization_id: UUID,
    agent_id: UUID,
    data: ToolRequestEvaluation,
    hashed_request: str,
    request_id: str | None,
    outcome: DecisionOutcome,
    reason_code: str,
    permission_id: UUID | None = None,
    matches: list[dict[str, Any]] | None = None,
    evidence: dict[str, Any] | None = None,
    security_findings: list[DetectedFinding] | None = None,
) -> PolicyDecision:
    decision = PolicyDecision(
        organization_id=organization_id,
        agent_id=agent_id,
        requested_tool_id=data.tool_id,
        operation=data.operation,
        environment=data.environment,
        idempotency_key=data.idempotency_key,
        request_id=request_id,
        request_hash=hashed_request,
        arguments_hash=canonical_hash(data.arguments),
        outcome=outcome,
        reason_code=reason_code,
        permission_id=permission_id,
        matched_policy_versions=matches or [],
        evidence_json=evidence or {},
    )
    session.add(decision)
    try:
        await session.flush()
        for finding in security_findings or []:
            session.add(
                SecurityFinding(
                    organization_id=organization_id,
                    decision_id=decision.id,
                    detector_id=finding.detector_id,
                    detector_version_id=finding.detector_version_id,
                    detector_kind=finding.detector_kind,
                    category=finding.category,
                    severity=finding.severity,
                    action=finding.action,
                    reason_code=finding.reason_code,
                    location=finding.location,
                    fingerprint=finding.fingerprint,
                    occurrence_count=finding.occurrence_count,
                )
            )
        if outcome == DecisionOutcome.REQUIRE_APPROVAL:
            approval = ApprovalRequest(
                organization_id=organization_id,
                decision_id=decision.id,
                agent_id=agent_id,
                requested_tool_id=data.tool_id,
                status=ApprovalStatus.PENDING,
                expires_at=datetime.now(UTC) + timedelta(hours=get_settings().approval_ttl_hours),
            )
            session.add(approval)
            await session.flush()
            record_audit(
                session,
                organization_id=organization_id,
                actor_type=ActorType.AGENT,
                actor_id=agent_id,
                action="approval.create",
                target_type="approval_request",
                target_id=approval.id,
                after={
                    "decision_id": decision.id,
                    "status": ApprovalStatus.PENDING,
                    "expires_at": approval.expires_at,
                },
                request_id=request_id,
            )
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await session.scalar(
            select(PolicyDecision).where(
                PolicyDecision.organization_id == organization_id,
                PolicyDecision.agent_id == agent_id,
                PolicyDecision.idempotency_key == data.idempotency_key,
            )
        )
        if existing is not None and existing.request_hash == hashed_request:
            return existing
        raise ConflictError("Idempotency key was already used for a different request") from None
    await session.refresh(decision)
    return decision


async def evaluate_tool_request(
    session: AsyncSession,
    *,
    agent: Agent,
    data: ToolRequestEvaluation,
    request_id: str | None = None,
    evaluated_at: datetime | None = None,
) -> PolicyDecision:
    hashed_request = request_hash(data)
    existing = await session.scalar(
        select(PolicyDecision).where(
            PolicyDecision.organization_id == agent.organization_id,
            PolicyDecision.agent_id == agent.id,
            PolicyDecision.idempotency_key == data.idempotency_key,
        )
    )
    if existing is not None:
        if existing.request_hash != hashed_request:
            raise ConflictError("Idempotency key was already used for a different request")
        return existing

    # PostgreSQL is the authoritative counter store. Serializing evaluations per
    # agent prevents concurrent requests from stepping past the same limit.
    await acquire_agent_evaluation_lock(session, agent.id)
    existing = await session.scalar(
        select(PolicyDecision).where(
            PolicyDecision.organization_id == agent.organization_id,
            PolicyDecision.agent_id == agent.id,
            PolicyDecision.idempotency_key == data.idempotency_key,
        )
    )
    if existing is not None:
        if existing.request_hash != hashed_request:
            raise ConflictError("Idempotency key was already used for a different request")
        return existing

    tool = await session.scalar(
        select(Tool).where(
            Tool.id == data.tool_id,
            Tool.organization_id == agent.organization_id,
        )
    )
    if tool is None:
        return await _store_decision(
            session,
            organization_id=agent.organization_id,
            agent_id=agent.id,
            data=data,
            hashed_request=hashed_request,
            request_id=request_id,
            outcome=DecisionOutcome.DENY,
            reason_code="TOOL_UNAVAILABLE",
        )

    schema_error_iterator = Draft202012Validator(tool.input_schema).iter_errors(  # pyright: ignore[reportUnknownMemberType]
        data.arguments
    )
    schema_errors: list[JsonSchemaValidationError] = sorted(
        schema_error_iterator,
        key=lambda error: list(error.absolute_path),
    )
    if schema_errors:
        sanitized_errors = [
            {
                "path": ".".join(str(item) for item in error.absolute_path),
                "validator": str(error.validator),
            }
            for error in schema_errors[:20]
        ]
        return await _store_decision(
            session,
            organization_id=agent.organization_id,
            agent_id=agent.id,
            data=data,
            hashed_request=hashed_request,
            request_id=request_id,
            outcome=DecisionOutcome.DENY,
            reason_code="INPUT_SCHEMA_INVALID",
            evidence={"validation_errors": sanitized_errors},
        )

    permission = await check_permission(
        session,
        organization_id=agent.organization_id,
        agent_id=agent.id,
        tool_id=tool.id,
        operation=data.operation,
        environment=data.environment,
    )
    if not permission.allowed:
        return await _store_decision(
            session,
            organization_id=agent.organization_id,
            agent_id=agent.id,
            data=data,
            hashed_request=hashed_request,
            request_id=request_id,
            outcome=DecisionOutcome.DENY,
            reason_code="PERMISSION_DENIED",
        )

    now = evaluated_at or datetime.now(UTC)
    reliability = await evaluate_reliability(
        session,
        agent=agent,
        request_hash=hashed_request,
        evaluated_at=now,
    )
    if not reliability.allowed:
        return await _store_decision(
            session,
            organization_id=agent.organization_id,
            agent_id=agent.id,
            data=data,
            hashed_request=hashed_request,
            request_id=request_id,
            outcome=DecisionOutcome.DENY,
            reason_code=reliability.reason_code or "RELIABILITY_CHECK_FAILED",
            permission_id=permission.permission_id,
            evidence={"reliability": reliability.evidence},
        )

    detector_evaluation = await evaluate_security_detectors(
        session,
        organization_id=agent.organization_id,
        agent_id=agent.id,
        tool_id=tool.id,
        operation=data.operation,
        environment=data.environment,
        arguments=data.arguments,
    )
    detector_denials = [
        finding
        for finding in detector_evaluation.findings
        if finding.action.value == DecisionOutcome.DENY.value
    ]
    detector_approvals = [
        finding
        for finding in detector_evaluation.findings
        if finding.action.value == DecisionOutcome.REQUIRE_APPROVAL.value
    ]
    finding_evidence = [finding.evidence() for finding in detector_evaluation.findings]

    rows = (
        await session.execute(
            select(Policy, PolicyVersion)
            .join(
                PolicyVersion,
                (PolicyVersion.policy_id == Policy.id)
                & (PolicyVersion.version == Policy.current_version),
            )
            .where(
                Policy.organization_id == agent.organization_id,
                Policy.status == PolicyStatus.ACTIVE,
            )
            .order_by(Policy.priority, Policy.id)
        )
    ).all()
    matches: list[dict[str, Any]] = []
    winning_deny: tuple[Policy, PolicyVersion, PolicyDocument] | None = None
    winning_approval: tuple[Policy, PolicyVersion, PolicyDocument] | None = None
    evaluated_versions: list[dict[str, Any]] = []
    for policy, version in rows:
        evaluated_versions.append(
            {
                "policy_id": str(policy.id),
                "policy_version_id": str(version.id),
                "version": version.version,
            }
        )
        try:
            document = PolicyDocument.model_validate(version.document_json)
        except PydanticValidationError:
            return await _store_decision(
                session,
                organization_id=agent.organization_id,
                agent_id=agent.id,
                data=data,
                hashed_request=hashed_request,
                request_id=request_id,
                outcome=DecisionOutcome.DENY,
                reason_code="POLICY_CONFIGURATION_INVALID",
                permission_id=permission.permission_id,
                evidence={
                    "policy_id": str(policy.id),
                    "version": version.version,
                    "evaluated_policy_versions": evaluated_versions,
                    "evaluated_detector_versions": detector_evaluation.evaluated_versions,
                    "security_findings": finding_evidence,
                    "reliability": reliability.evidence,
                },
                security_findings=detector_evaluation.findings,
            )
        if not scope_matches(
            document,
            agent_id=agent.id,
            tool_id=tool.id,
            operation=data.operation,
            environment=data.environment,
        ):
            continue
        if not all(
            condition_matches(condition, data.arguments, now) for condition in document.conditions
        ):
            continue
        match = {
            "policy_id": str(policy.id),
            "policy_version_id": str(version.id),
            "version": version.version,
            "effect": document.effect.value,
            "reason_code": document.reason_code,
        }
        matches.append(match)
        candidate = (policy, version, document)
        if document.effect == PolicyEffect.DENY and winning_deny is None:
            winning_deny = candidate
        elif document.effect == PolicyEffect.REQUIRE_APPROVAL and winning_approval is None:
            winning_approval = candidate

    if detector_denials:
        outcome = DecisionOutcome.DENY
        reason_code = detector_denials[0].reason_code
    elif winning_deny is not None:
        outcome = DecisionOutcome.DENY
        reason_code = winning_deny[2].reason_code
    elif detector_approvals:
        outcome = DecisionOutcome.REQUIRE_APPROVAL
        reason_code = detector_approvals[0].reason_code
    elif winning_approval is not None:
        outcome = DecisionOutcome.REQUIRE_APPROVAL
        reason_code = winning_approval[2].reason_code
    else:
        outcome = DecisionOutcome.ALLOW
        reason_code = "POLICY_CHECKS_PASSED"

    return await _store_decision(
        session,
        organization_id=agent.organization_id,
        agent_id=agent.id,
        data=data,
        hashed_request=hashed_request,
        request_id=request_id,
        outcome=outcome,
        reason_code=reason_code,
        permission_id=permission.permission_id,
        matches=matches,
        evidence={
            "schema_valid": True,
            "permission_granted": True,
            "evaluated_policy_versions": evaluated_versions,
            "evaluated_detector_versions": detector_evaluation.evaluated_versions,
            "security_findings": finding_evidence,
            "reliability": reliability.evidence,
        },
        security_findings=detector_evaluation.findings,
    )


async def list_decisions(
    session: AsyncSession, organization_id: UUID, limit: int
) -> list[PolicyDecision]:
    result = await session.scalars(
        select(PolicyDecision)
        .where(PolicyDecision.organization_id == organization_id)
        .order_by(PolicyDecision.created_at.desc())
        .limit(limit)
    )
    return list(result.all())


async def get_decision(
    session: AsyncSession, organization_id: UUID, decision_id: UUID
) -> PolicyDecision:
    decision = await session.scalar(
        select(PolicyDecision).where(
            PolicyDecision.id == decision_id,
            PolicyDecision.organization_id == organization_id,
        )
    )
    if decision is None:
        raise NotFoundError("Decision")
    return decision
