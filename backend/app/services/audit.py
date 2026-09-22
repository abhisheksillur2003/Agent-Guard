import hashlib
import json
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import ActorType, AuditLog


def snapshot_hash(value: Any | None) -> str | None:
    if value is None:
        return None
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def record_audit(
    session: AsyncSession,
    *,
    organization_id: UUID,
    actor_type: ActorType,
    actor_id: UUID | None,
    action: str,
    target_type: str,
    target_id: UUID | None,
    before: Any | None = None,
    after: Any | None = None,
    details: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> AuditLog:
    event = AuditLog(
        organization_id=organization_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        before_hash=snapshot_hash(before),
        after_hash=snapshot_hash(after),
        details_json=details or {},
        request_id=request_id,
    )
    session.add(event)
    return event
