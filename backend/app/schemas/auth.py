from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr

from backend.app.models.enums import UserRole, UserStatus
from backend.app.schemas.common import ORMModel


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class CurrentUserResponse(ORMModel):
    id: UUID
    organization_id: UUID
    email: EmailStr
    role: UserRole
    status: UserStatus
    created_at: datetime
    last_login_at: datetime | None


class OrganizationResponse(ORMModel):
    id: UUID
    name: str
    slug: str
    created_at: datetime
