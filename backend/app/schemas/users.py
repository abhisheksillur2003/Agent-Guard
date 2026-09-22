from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from backend.app.models.enums import UserRole, UserStatus
from backend.app.schemas.common import ORMModel


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)
    role: UserRole = UserRole.DEVELOPER


class UserUpdate(BaseModel):
    role: UserRole | None = None
    status: UserStatus | None = None


class UserResponse(ORMModel):
    id: UUID
    organization_id: UUID
    email: EmailStr
    role: UserRole
    status: UserStatus
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None
