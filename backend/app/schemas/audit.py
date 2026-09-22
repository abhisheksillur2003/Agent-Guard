from datetime import datetime
from typing import Any
from uuid import UUID

from backend.app.models.enums import ActorType
from backend.app.schemas.common import ORMModel


class AuditLogResponse(ORMModel):
    id: UUID
    organization_id: UUID
    actor_type: ActorType
    actor_id: UUID | None
    action: str
    target_type: str
    target_id: UUID | None
    before_hash: str | None
    after_hash: str | None
    details_json: dict[str, Any]
    request_id: str | None
    created_at: datetime
