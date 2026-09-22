from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.errors import ConflictError, NotFoundError, ValidationError
from backend.app.core.security import hash_password
from backend.app.models import ActorType, User, UserRole, UserStatus
from backend.app.schemas.users import UserCreate, UserUpdate
from backend.app.services.audit import record_audit


def user_snapshot(user: User) -> dict[str, Any]:
    return {"email": user.email, "role": user.role, "status": user.status}


async def get_user(session: AsyncSession, organization_id: UUID, user_id: UUID) -> User:
    user = await session.scalar(
        select(User).where(User.id == user_id, User.organization_id == organization_id)
    )
    if user is None:
        raise NotFoundError("User")
    return user


async def list_users(session: AsyncSession, organization_id: UUID) -> list[User]:
    result = await session.scalars(
        select(User).where(User.organization_id == organization_id).order_by(User.created_at.desc())
    )
    return list(result.all())


async def create_user(
    session: AsyncSession,
    *,
    organization_id: UUID,
    actor_id: UUID,
    data: UserCreate,
    request_id: str | None,
) -> User:
    normalized_email = data.email.strip().lower()
    duplicate = await session.scalar(
        select(User.id).where(
            User.organization_id == organization_id,
            User.email == normalized_email,
        )
    )
    if duplicate is not None:
        raise ConflictError("A user with this email already exists")

    user = User(
        organization_id=organization_id,
        email=normalized_email,
        password_hash=hash_password(data.password),
        role=data.role,
        status=UserStatus.ACTIVE,
    )
    session.add(user)
    await session.flush()
    record_audit(
        session,
        organization_id=organization_id,
        actor_type=ActorType.USER,
        actor_id=actor_id,
        action="user.create",
        target_type="user",
        target_id=user.id,
        after=user_snapshot(user),
        request_id=request_id,
    )
    await session.commit()
    await session.refresh(user)
    return user


async def update_user(
    session: AsyncSession,
    *,
    organization_id: UUID,
    user_id: UUID,
    actor_id: UUID,
    data: UserUpdate,
    request_id: str | None,
) -> User:
    user = await get_user(session, organization_id, user_id)
    changes = data.model_dump(exclude_unset=True)
    removes_active_admin = (
        user.role == UserRole.ADMIN
        and user.status == UserStatus.ACTIVE
        and (
            changes.get("role", UserRole.ADMIN) != UserRole.ADMIN
            or changes.get("status", UserStatus.ACTIVE) != UserStatus.ACTIVE
        )
    )
    if removes_active_admin:
        active_admin_count = await session.scalar(
            select(func.count())
            .select_from(User)
            .where(
                User.organization_id == organization_id,
                User.role == UserRole.ADMIN,
                User.status == UserStatus.ACTIVE,
            )
        )
        if active_admin_count is None or active_admin_count <= 1:
            raise ValidationError("The organization must retain at least one active administrator")

    before = user_snapshot(user)
    for field, value in changes.items():
        setattr(user, field, value)
    record_audit(
        session,
        organization_id=organization_id,
        actor_type=ActorType.USER,
        actor_id=actor_id,
        action="user.update",
        target_type="user",
        target_id=user.id,
        before=before,
        after=user_snapshot(user),
        request_id=request_id,
    )
    await session.commit()
    await session.refresh(user)
    return user
