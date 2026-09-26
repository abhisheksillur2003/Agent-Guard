from typing import Any
from uuid import UUID

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.errors import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ValidationError,
)
from backend.app.models import ActorType, Tool, UserRole
from backend.app.schemas.tools import ToolCreate, ToolUpdate
from backend.app.services.audit import record_audit
from backend.app.services.tool_adapters import (
    AdapterMetadata,
    adapter_metadata,
    get_adapter,
    validate_adapter_capabilities,
)


def tool_snapshot(tool: Tool) -> dict[str, Any]:
    return {
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.input_schema,
        "risk_class": tool.risk_class,
        "capability_flags": tool.capability_flags,
        "status": tool.status,
        "adapter_name": tool.adapter_name,
        "adapter_version": tool.adapter_version,
        "execution_timeout_seconds": tool.execution_timeout_seconds,
    }


def validate_json_schema(schema: dict[str, Any]) -> None:
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ValidationError(f"Invalid JSON Schema: {exc.message}") from exc


async def get_tool(session: AsyncSession, organization_id: UUID, tool_id: UUID) -> Tool:
    tool = await session.scalar(
        select(Tool).where(Tool.id == tool_id, Tool.organization_id == organization_id)
    )
    if tool is None:
        raise NotFoundError("Tool")
    return tool


async def list_tools(session: AsyncSession, organization_id: UUID) -> list[Tool]:
    result = await session.scalars(
        select(Tool).where(Tool.organization_id == organization_id).order_by(Tool.created_at.desc())
    )
    return list(result.all())


def list_tool_adapters() -> list[AdapterMetadata]:
    return adapter_metadata()


async def create_tool(
    session: AsyncSession,
    *,
    organization_id: UUID,
    actor_id: UUID,
    data: ToolCreate,
    request_id: str | None,
) -> Tool:
    validate_json_schema(data.input_schema)
    adapter = get_adapter(data.adapter_name, data.adapter_version)
    validate_adapter_capabilities(adapter, data.capability_flags)
    duplicate = await session.scalar(
        select(Tool.id).where(
            Tool.organization_id == organization_id,
            Tool.name == data.name,
        )
    )
    if duplicate is not None:
        raise ConflictError("A tool with this name already exists")
    payload = data.model_dump(mode="json")
    tool = Tool(organization_id=organization_id, **payload)
    session.add(tool)
    await session.flush()
    record_audit(
        session,
        organization_id=organization_id,
        actor_type=ActorType.USER,
        actor_id=actor_id,
        action="tool.create",
        target_type="tool",
        target_id=tool.id,
        after=tool_snapshot(tool),
        request_id=request_id,
    )
    await session.commit()
    await session.refresh(tool)
    return tool


async def update_tool(
    session: AsyncSession,
    *,
    organization_id: UUID,
    tool_id: UUID,
    actor_id: UUID,
    actor_role: UserRole,
    data: ToolUpdate,
    request_id: str | None,
) -> Tool:
    tool = await get_tool(session, organization_id, tool_id)
    changes = data.model_dump(exclude_unset=True, mode="json")
    protected_fields = {
        "risk_class",
        "capability_flags",
        "status",
        "adapter_name",
        "adapter_version",
        "execution_timeout_seconds",
    }
    if actor_role != UserRole.ADMIN and protected_fields.intersection(changes):
        raise AuthorizationError("Only administrators may change tool risk or status fields")
    if "input_schema" in changes:
        validate_json_schema(changes["input_schema"])
    adapter_name = str(changes.get("adapter_name", tool.adapter_name))
    adapter_version = str(changes.get("adapter_version", tool.adapter_version))
    adapter = get_adapter(adapter_name, adapter_version)
    capabilities = changes.get("capability_flags", tool.capability_flags)
    validate_adapter_capabilities(adapter, capabilities)
    if "name" in changes and changes["name"] != tool.name:
        duplicate = await session.scalar(
            select(Tool.id).where(
                Tool.organization_id == organization_id,
                Tool.name == changes["name"],
                Tool.id != tool.id,
            )
        )
        if duplicate is not None:
            raise ConflictError("A tool with this name already exists")
    before = tool_snapshot(tool)
    for field, value in changes.items():
        setattr(tool, field, value)
    record_audit(
        session,
        organization_id=organization_id,
        actor_type=ActorType.USER,
        actor_id=actor_id,
        action="tool.update",
        target_type="tool",
        target_id=tool.id,
        before=before,
        after=tool_snapshot(tool),
        request_id=request_id,
    )
    await session.commit()
    await session.refresh(tool)
    return tool
