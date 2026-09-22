from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "admin"
    DEVELOPER = "developer"
    APPROVER = "approver"
    READ_ONLY = "read_only"


class UserStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class AgentStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class CredentialStatus(StrEnum):
    ACTIVE = "active"
    REVOKED = "revoked"


class ToolStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class RiskTier(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ToolCapability(StrEnum):
    READ_ONLY = "read_only"
    WRITE = "write"
    DESTRUCTIVE = "destructive"
    FINANCIAL = "financial"
    EXTERNAL_EGRESS = "external_egress"
    CODE_EXECUTION = "code_execution"


class ActorType(StrEnum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"


class PolicyStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class PolicyEffect(StrEnum):
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


class DecisionOutcome(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    REQUIRE_APPROVAL = "require_approval"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ExecutionStatus(StrEnum):
    AUTHORIZED = "authorized"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


class DetectorStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"


class DetectorKind(StrEnum):
    SECRET = "secret"
    PII = "pii"
    PROMPT_INJECTION = "prompt_injection"


class FindingSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FindingAction(StrEnum):
    RECORD = "record"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"
