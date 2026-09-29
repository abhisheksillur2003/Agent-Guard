from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.errors import ConflictError, NotFoundError, ValidationError
from backend.app.models import (
    Agent,
    AgentCredential,
    AgentPermission,
    AgentStatus,
    CredentialStatus,
    DetectorKind,
    DetectorStatus,
    FindingAction,
    FindingSeverity,
    Policy,
    PolicyEffect,
    PolicyStatus,
    RiskTier,
    SecurityDetector,
    Tool,
    ToolCapability,
    ToolStatus,
    User,
    UserRole,
    UserStatus,
)
from backend.app.schemas.agents import AgentCreate
from backend.app.schemas.permissions import PermissionUpsert
from backend.app.schemas.policies import (
    NumberGreaterThanCondition,
    PolicyCreate,
    PolicyDocument,
    PolicyScope,
)
from backend.app.schemas.security import (
    DetectorCreate,
    PiiDetectorDocument,
    PromptInjectionDetectorDocument,
    SecretDetectorDocument,
)
from backend.app.schemas.tools import ToolCreate
from backend.app.services import agents as agent_service
from backend.app.services import detectors as detector_service
from backend.app.services import permissions as permission_service
from backend.app.services import policies as policy_service
from backend.app.services import tools as tool_service

DEMO_AGENT_NAME = "Local Support Agent"
DEMO_TOOL_NAME = "Local Refund Simulator"
DEMO_POLICY_NAME = "Review large local refunds"
DEMO_SECRET_DETECTOR_NAME = "Block secrets in local requests"
DEMO_PII_DETECTOR_NAME = "Record PII in local requests"
DEMO_PROMPT_DETECTOR_NAME = "Review prompt manipulation"

DEMO_TOOL_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "properties": {
        "order_id": {"type": "string", "minLength": 1, "maxLength": 80},
        "amount": {"type": "number", "minimum": 0, "maximum": 100000},
        "customer_message": {"type": "string", "maxLength": 2000},
    },
    "required": ["order_id", "amount"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class LocalDemoResult:
    organization_id: UUID
    admin_id: UUID
    agent_id: UUID
    tool_id: UUID
    credential: str | None
    created: tuple[str, ...]


async def _local_admin(session: AsyncSession, email: str) -> User:
    normalized_email = email.strip().lower()
    users = list(
        (
            await session.scalars(
                select(User).where(
                    User.email == normalized_email,
                    User.role == UserRole.ADMIN,
                    User.status == UserStatus.ACTIVE,
                )
            )
        ).all()
    )
    if not users:
        raise NotFoundError("Active administrator")
    if len(users) != 1:
        raise ConflictError("Administrator email must identify exactly one organization")
    return users[0]


async def _agent(session: AsyncSession, admin: User, created: list[str]) -> Agent:
    agent = await session.scalar(
        select(Agent).where(
            Agent.organization_id == admin.organization_id,
            Agent.name == DEMO_AGENT_NAME,
        )
    )
    if agent is not None:
        if (
            agent.owner_user_id != admin.id
            or agent.status != AgentStatus.ACTIVE
            or agent.risk_tier != RiskTier.MEDIUM
            or agent.allowed_environments != ["local"]
        ):
            raise ConflictError(f"Existing agent '{DEMO_AGENT_NAME}' is not the local demo agent")
        return agent
    agent = await agent_service.create_agent(
        session,
        organization_id=admin.organization_id,
        actor_id=admin.id,
        data=AgentCreate(
            name=DEMO_AGENT_NAME,
            description="A local-only agent for exercising AgentGuard's guarded execution flow.",
            owner_user_id=admin.id,
            risk_tier=RiskTier.MEDIUM,
            allowed_environments=["local"],
        ),
        request_id="local-demo-bootstrap",
    )
    created.append("agent")
    return agent


async def _tool(session: AsyncSession, admin: User, created: list[str]) -> Tool:
    tool = await session.scalar(
        select(Tool).where(
            Tool.organization_id == admin.organization_id,
            Tool.name == DEMO_TOOL_NAME,
        )
    )
    if tool is not None:
        if (
            tool.status != ToolStatus.ACTIVE
            or tool.risk_class != RiskTier.HIGH
            or set(tool.capability_flags)
            != {ToolCapability.WRITE.value, ToolCapability.FINANCIAL.value}
            or tool.adapter_name != "safe_echo"
            or tool.adapter_version != "1"
            or tool.input_schema != DEMO_TOOL_SCHEMA
        ):
            raise ConflictError(f"Existing tool '{DEMO_TOOL_NAME}' is not the local demo tool")
        return tool
    tool = await tool_service.create_tool(
        session,
        organization_id=admin.organization_id,
        actor_id=admin.id,
        data=ToolCreate(
            name=DEMO_TOOL_NAME,
            description="Validates a synthetic refund and returns only safe argument metadata.",
            input_schema=DEMO_TOOL_SCHEMA,
            risk_class=RiskTier.HIGH,
            capability_flags=[ToolCapability.WRITE, ToolCapability.FINANCIAL],
            adapter_name="safe_echo",
            adapter_version="1",
            execution_timeout_seconds=10,
        ),
        request_id="local-demo-bootstrap",
    )
    created.append("tool")
    return tool


async def _permission(
    session: AsyncSession, admin: User, agent: Agent, tool: Tool, created: list[str]
) -> None:
    permission = await session.scalar(
        select(AgentPermission).where(
            AgentPermission.agent_id == agent.id,
            AgentPermission.tool_id == tool.id,
        )
    )
    if permission is not None:
        if permission.operations != ["refund"] or permission.constraints_json:
            raise ConflictError("Existing local demo permission has different constraints")
        return
    await permission_service.upsert_permission(
        session,
        organization_id=admin.organization_id,
        agent_id=agent.id,
        tool_id=tool.id,
        actor_id=admin.id,
        data=PermissionUpsert(operations=["refund"]),
        request_id="local-demo-bootstrap",
    )
    created.append("permission")


def _policy_document(agent: Agent, tool: Tool) -> PolicyDocument:
    return PolicyDocument(
        scope=PolicyScope(
            agent_ids=[agent.id],
            tool_ids=[tool.id],
            environments=["local"],
            operations=["refund"],
        ),
        effect=PolicyEffect.REQUIRE_APPROVAL,
        reason_code="LARGE_REFUND_REVIEW",
        conditions=[NumberGreaterThanCondition(type="number_gt", path="amount", value=500)],
    )


async def _policy(
    session: AsyncSession, admin: User, agent: Agent, tool: Tool, created: list[str]
) -> None:
    expected = _policy_document(agent, tool)
    policy = await session.scalar(
        select(Policy).where(
            Policy.organization_id == admin.organization_id,
            Policy.name == DEMO_POLICY_NAME,
        )
    )
    if policy is not None:
        current = await policy_service.get_policy_version(
            session, policy.id, policy.current_version
        )
        if policy.status != PolicyStatus.ACTIVE or current.document_json != expected.model_dump(
            mode="json"
        ):
            raise ConflictError(f"Existing policy '{DEMO_POLICY_NAME}' has different rules")
        return
    await policy_service.create_policy(
        session,
        organization_id=admin.organization_id,
        actor_id=admin.id,
        data=PolicyCreate(
            name=DEMO_POLICY_NAME,
            description="Requires human review when a synthetic local refund exceeds 500.",
            priority=100,
            document=expected,
        ),
        request_id="local-demo-bootstrap",
    )
    created.append("policy")


async def _detector(
    session: AsyncSession,
    *,
    admin: User,
    name: str,
    description: str,
    priority: int,
    document: SecretDetectorDocument | PiiDetectorDocument | PromptInjectionDetectorDocument,
    created: list[str],
) -> None:
    detector = await session.scalar(
        select(SecurityDetector).where(
            SecurityDetector.organization_id == admin.organization_id,
            SecurityDetector.name == name,
        )
    )
    if detector is not None:
        current = await detector_service.get_detector_version(
            session, detector.id, detector.current_version
        )
        if detector.status != DetectorStatus.ACTIVE or current.document_json != document.model_dump(
            mode="json"
        ):
            raise ConflictError(f"Existing detector '{name}' has different rules")
        return
    await detector_service.create_detector(
        session,
        organization_id=admin.organization_id,
        actor_id=admin.id,
        data=DetectorCreate(
            name=name,
            description=description,
            priority=priority,
            document=document,
        ),
        request_id="local-demo-bootstrap",
    )
    created.append(f"detector:{name}")


async def _detectors(
    session: AsyncSession, admin: User, agent: Agent, tool: Tool, created: list[str]
) -> None:
    scope = PolicyScope(
        agent_ids=[agent.id],
        tool_ids=[tool.id],
        environments=["local"],
        operations=["refund"],
    )
    await _detector(
        session,
        admin=admin,
        name=DEMO_SECRET_DETECTOR_NAME,
        description="Blocks synthetic requests containing credential-shaped values.",
        priority=10,
        document=SecretDetectorDocument(
            kind=DetectorKind.SECRET,
            scope=scope,
            action=FindingAction.DENY,
            severity=FindingSeverity.CRITICAL,
            reason_code="LOCAL_SECRET_DETECTED",
            secret_types=[
                "aws_access_key",
                "jwt",
                "private_key",
                "generic_api_key",
                "high_entropy",
            ],
        ),
        created=created,
    )
    await _detector(
        session,
        admin=admin,
        name=DEMO_PII_DETECTOR_NAME,
        description="Records sanitized PII evidence without storing the matched value.",
        priority=20,
        document=PiiDetectorDocument(
            kind=DetectorKind.PII,
            scope=scope,
            action=FindingAction.RECORD,
            severity=FindingSeverity.MEDIUM,
            reason_code="LOCAL_PII_RECORDED",
            entities=["email", "phone", "credit_card", "ipv4", "india_aadhaar"],
        ),
        created=created,
    )
    await _detector(
        session,
        admin=admin,
        name=DEMO_PROMPT_DETECTOR_NAME,
        description="Routes prompt-manipulation phrases to a human approver.",
        priority=30,
        document=PromptInjectionDetectorDocument(
            kind=DetectorKind.PROMPT_INJECTION,
            scope=scope,
            action=FindingAction.REQUIRE_APPROVAL,
            severity=FindingSeverity.HIGH,
            reason_code="LOCAL_PROMPT_REVIEW",
            rules=[
                "ignore_instructions",
                "system_prompt_extraction",
                "tool_override",
                "role_impersonation",
            ],
        ),
        created=created,
    )


async def _credential(
    session: AsyncSession, admin: User, agent: Agent, created: list[str]
) -> str | None:
    existing = await session.scalar(
        select(AgentCredential.id).where(
            AgentCredential.agent_id == agent.id,
            AgentCredential.status == CredentialStatus.ACTIVE,
        )
    )
    if existing is not None:
        return None
    credential, _ = await agent_service.issue_agent_credential(
        session,
        organization_id=admin.organization_id,
        agent_id=agent.id,
        actor_id=admin.id,
        expires_at=None,
        rotate=False,
        request_id="local-demo-bootstrap",
    )
    created.append("agent_credential")
    return credential


async def seed_local_demo(
    session: AsyncSession,
    *,
    admin_email: str,
    environment: str,
    issue_credential: bool = True,
) -> LocalDemoResult:
    if environment != "local":
        raise ValidationError("The demo workspace can only be created in the local environment")
    created: list[str] = []
    admin = await _local_admin(session, admin_email)
    agent = await _agent(session, admin, created)
    tool = await _tool(session, admin, created)
    await _permission(session, admin, agent, tool, created)
    await _policy(session, admin, agent, tool, created)
    await _detectors(session, admin, agent, tool, created)
    credential = await _credential(session, admin, agent, created) if issue_credential else None
    return LocalDemoResult(
        organization_id=admin.organization_id,
        admin_id=admin.id,
        agent_id=agent.id,
        tool_id=tool.id,
        credential=credential,
        created=tuple(created),
    )
