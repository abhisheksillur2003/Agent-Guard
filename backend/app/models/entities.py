from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base
from backend.app.models.enums import (
    ActorType,
    AgentStatus,
    ApprovalStatus,
    CredentialStatus,
    DecisionOutcome,
    DetectorKind,
    DetectorStatus,
    ExecutionStatus,
    FindingAction,
    FindingSeverity,
    PolicyStatus,
    RiskTier,
    ToolStatus,
    UserRole,
    UserStatus,
)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Organization(TimestampMixin, Base):
    __tablename__ = "organizations"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    users: Mapped[list[User]] = relationship(back_populates="organization")


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("organization_id", "email", name="uq_users_org_email"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(String(20), nullable=False)
    status: Mapped[UserStatus] = mapped_column(
        String(20), default=UserStatus.ACTIVE, nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    organization: Mapped[Organization] = relationship(back_populates="users")


class Agent(TimestampMixin, Base):
    __tablename__ = "agents"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_agents_org_name"),
        Index("ix_agents_org_status", "organization_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    owner_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[AgentStatus] = mapped_column(
        String(20), default=AgentStatus.ACTIVE, nullable=False
    )
    risk_tier: Mapped[RiskTier] = mapped_column(String(20), default=RiskTier.MEDIUM, nullable=False)
    allowed_environments: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    budget_config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)

    credentials: Mapped[list[AgentCredential]] = relationship(
        back_populates="agent", cascade="all, delete-orphan"
    )


class AgentCredential(Base):
    __tablename__ = "agent_credentials"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key_prefix: Mapped[str] = mapped_column(String(24), nullable=False, unique=True)
    secret_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[CredentialStatus] = mapped_column(
        String(20), default=CredentialStatus.ACTIVE, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    agent: Mapped[Agent] = relationship(back_populates="credentials")


class Tool(TimestampMixin, Base):
    __tablename__ = "tools"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_tools_org_name"),
        Index("ix_tools_org_status", "organization_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    input_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    risk_class: Mapped[RiskTier] = mapped_column(String(20), nullable=False)
    capability_flags: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    status: Mapped[ToolStatus] = mapped_column(
        String(20), default=ToolStatus.ACTIVE, nullable=False
    )
    adapter_name: Mapped[str] = mapped_column(String(80), default="safe_echo", nullable=False)
    adapter_version: Mapped[str] = mapped_column(String(40), default="1", nullable=False)
    execution_timeout_seconds: Mapped[int] = mapped_column(nullable=False, default=10)


class AgentPermission(TimestampMixin, Base):
    __tablename__ = "agent_permissions"
    __table_args__ = (UniqueConstraint("agent_id", "tool_id", name="uq_permissions_agent_tool"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tool_id: Mapped[UUID] = mapped_column(
        ForeignKey("tools.id", ondelete="CASCADE"), nullable=False, index=True
    )
    operations: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    constraints_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_org_created", "organization_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    actor_type: Mapped[ActorType] = mapped_column(String(20), nullable=False)
    actor_id: Mapped[UUID | None]
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    target_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_id: Mapped[UUID | None]
    before_hash: Mapped[str | None] = mapped_column(String(64))
    after_hash: Mapped[str | None] = mapped_column(String(64))
    details_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Policy(TimestampMixin, Base):
    __tablename__ = "policies"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_policies_org_name"),
        Index("ix_policies_org_status", "organization_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[PolicyStatus] = mapped_column(
        String(20), default=PolicyStatus.ACTIVE, nullable=False
    )
    priority: Mapped[int] = mapped_column(nullable=False, default=100)
    current_version: Mapped[int] = mapped_column(nullable=False, default=1)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))

    versions: Mapped[list[PolicyVersion]] = relationship(
        back_populates="policy", cascade="all, delete-orphan"
    )


class PolicyVersion(Base):
    __tablename__ = "policy_versions"
    __table_args__ = (UniqueConstraint("policy_id", "version", name="uq_policy_versions_number"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    policy_id: Mapped[UUID] = mapped_column(
        ForeignKey("policies.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(nullable=False)
    document_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    policy: Mapped[Policy] = relationship(back_populates="versions")


class PolicyDecision(Base):
    __tablename__ = "policy_decisions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "agent_id",
            "idempotency_key",
            name="uq_policy_decisions_idempotency",
        ),
        Index("ix_policy_decisions_org_created", "organization_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="RESTRICT"), nullable=False
    )
    requested_tool_id: Mapped[UUID] = mapped_column(nullable=False)
    operation: Mapped[str] = mapped_column(String(120), nullable=False)
    environment: Mapped[str] = mapped_column(String(80), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(80))
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    arguments_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[DecisionOutcome] = mapped_column(String(24), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    permission_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agent_permissions.id", ondelete="SET NULL")
    )
    matched_policy_versions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, nullable=False
    )
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ApprovalRequest(TimestampMixin, Base):
    __tablename__ = "approval_requests"
    __table_args__ = (Index("ix_approval_requests_org_status", "organization_id", "status"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    decision_id: Mapped[UUID] = mapped_column(
        ForeignKey("policy_decisions.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="RESTRICT"), nullable=False
    )
    requested_tool_id: Mapped[UUID] = mapped_column(nullable=False)
    status: Mapped[ApprovalStatus] = mapped_column(
        String(24), default=ApprovalStatus.PENDING, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    decision_reason: Mapped[str | None] = mapped_column(Text)


class ToolExecution(Base):
    __tablename__ = "tool_executions"
    __table_args__ = (Index("ix_tool_executions_org_created", "organization_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    decision_id: Mapped[UUID] = mapped_column(
        ForeignKey("policy_decisions.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    approval_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("approval_requests.id", ondelete="RESTRICT"), unique=True
    )
    agent_id: Mapped[UUID] = mapped_column(
        ForeignKey("agents.id", ondelete="RESTRICT"), nullable=False
    )
    tool_id: Mapped[UUID] = mapped_column(
        ForeignKey("tools.id", ondelete="RESTRICT"), nullable=False
    )
    operation: Mapped[str] = mapped_column(String(120), nullable=False)
    environment: Mapped[str] = mapped_column(String(80), nullable=False)
    arguments_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[ExecutionStatus] = mapped_column(String(24), nullable=False)
    adapter_name: Mapped[str] = mapped_column(String(80), nullable=False)
    adapter_version: Mapped[str] = mapped_column(String(40), nullable=False)
    result_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(80))
    attempt_count: Mapped[int] = mapped_column(default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(default=1, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ExecutionEvent(Base):
    __tablename__ = "execution_events"
    __table_args__ = (
        UniqueConstraint("execution_id", "sequence", name="uq_execution_events_sequence"),
        Index("ix_execution_events_execution_created", "execution_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    execution_id: Mapped[UUID] = mapped_column(
        ForeignKey("tool_executions.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[ExecutionStatus] = mapped_column(String(24), nullable=False)
    details_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SecurityDetector(TimestampMixin, Base):
    __tablename__ = "security_detectors"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_security_detectors_org_name"),
        Index("ix_security_detectors_org_status", "organization_id", "status"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[DetectorStatus] = mapped_column(
        String(20), default=DetectorStatus.ACTIVE, nullable=False
    )
    priority: Mapped[int] = mapped_column(nullable=False, default=100)
    current_version: Mapped[int] = mapped_column(nullable=False, default=1)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))

    versions: Mapped[list[DetectorVersion]] = relationship(
        back_populates="detector", cascade="all, delete-orphan"
    )


class DetectorVersion(Base):
    __tablename__ = "detector_versions"
    __table_args__ = (
        UniqueConstraint("detector_id", "version", name="uq_detector_versions_number"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    detector_id: Mapped[UUID] = mapped_column(
        ForeignKey("security_detectors.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(nullable=False)
    document_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    detector: Mapped[SecurityDetector] = relationship(back_populates="versions")


class SecurityFinding(Base):
    __tablename__ = "security_findings"
    __table_args__ = (
        Index("ix_security_findings_org_created", "organization_id", "created_at"),
        Index("ix_security_findings_decision", "decision_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    decision_id: Mapped[UUID] = mapped_column(
        ForeignKey("policy_decisions.id", ondelete="CASCADE"), nullable=False
    )
    detector_id: Mapped[UUID] = mapped_column(
        ForeignKey("security_detectors.id", ondelete="RESTRICT"), nullable=False
    )
    detector_version_id: Mapped[UUID] = mapped_column(
        ForeignKey("detector_versions.id", ondelete="RESTRICT"), nullable=False
    )
    detector_kind: Mapped[DetectorKind] = mapped_column(String(32), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    severity: Mapped[FindingSeverity] = mapped_column(String(20), nullable=False)
    action: Mapped[FindingAction] = mapped_column(String(24), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    location: Mapped[str] = mapped_column(String(300), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    occurrence_count: Mapped[int] = mapped_column(nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
