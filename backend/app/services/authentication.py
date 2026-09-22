from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.errors import AuthenticationError, ConflictError, ValidationError
from backend.app.core.security import hash_password, verify_password
from backend.app.models import ActorType, Organization, User, UserRole, UserStatus
from backend.app.services.audit import record_audit


async def bootstrap_admin(
    session: AsyncSession,
    *,
    organization_name: str,
    organization_slug: str,
    email: str,
    password: str,
) -> tuple[Organization, User]:
    if len(password) < 12:
        raise ValidationError("Administrator password must contain at least 12 characters")

    normalized_email = email.strip().lower()
    normalized_slug = organization_slug.strip().lower()
    organization = await session.scalar(
        select(Organization).where(Organization.slug == normalized_slug)
    )
    if organization is None:
        organization = Organization(name=organization_name.strip(), slug=normalized_slug)
        session.add(organization)
        await session.flush()

    existing = await session.scalar(
        select(User).where(
            User.organization_id == organization.id,
            User.email == normalized_email,
        )
    )
    if existing is not None:
        raise ConflictError("An administrator with this email already exists")

    user = User(
        organization_id=organization.id,
        email=normalized_email,
        password_hash=hash_password(password),
        role=UserRole.ADMIN,
        status=UserStatus.ACTIVE,
    )
    session.add(user)
    await session.flush()
    record_audit(
        session,
        organization_id=organization.id,
        actor_type=ActorType.SYSTEM,
        actor_id=None,
        action="user.bootstrap_admin",
        target_type="user",
        target_id=user.id,
        after={"email": user.email, "role": user.role, "status": user.status},
    )
    await session.commit()
    await session.refresh(user)
    return organization, user


async def authenticate_user(session: AsyncSession, email: str, password: str) -> User:
    normalized_email = email.strip().lower()
    users = list((await session.scalars(select(User).where(User.email == normalized_email))).all())
    if len(users) != 1:
        raise AuthenticationError()
    user = users[0]
    if user.status != UserStatus.ACTIVE or not verify_password(password, user.password_hash):
        raise AuthenticationError()
    user.last_login_at = datetime.now(UTC)
    await session.commit()
    await session.refresh(user)
    return user
