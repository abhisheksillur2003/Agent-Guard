from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.errors import AuthenticationError, AuthorizationError
from backend.app.core.security import (
    agent_key_matches,
    decode_access_token,
    parse_agent_key,
)
from backend.app.db.session import get_session
from backend.app.models import (
    Agent,
    AgentCredential,
    AgentStatus,
    CredentialStatus,
    User,
    UserRole,
    UserStatus,
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)
agent_bearer = HTTPBearer(auto_error=False)

DatabaseSession = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    session: DatabaseSession,
) -> User:
    if token is None:
        raise AuthenticationError()
    payload = decode_access_token(token)
    try:
        user_id = UUID(str(payload["sub"]))
        organization_id = UUID(str(payload["org"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise AuthenticationError() from exc
    user = await session.scalar(
        select(User).where(User.id == user_id, User.organization_id == organization_id)
    )
    if user is None or user.status != UserStatus.ACTIVE:
        raise AuthenticationError()
    return user


def require_roles(*allowed_roles: UserRole) -> Callable[..., Awaitable[User]]:
    async def dependency(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if current_user.role not in allowed_roles:
            raise AuthorizationError()
        return current_user

    return dependency


async def get_current_agent(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(agent_bearer)],
    session: DatabaseSession,
) -> Agent:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError()
    prefix, secret = parse_agent_key(credentials.credentials)
    row = (
        await session.execute(
            select(AgentCredential, Agent)
            .join(Agent, Agent.id == AgentCredential.agent_id)
            .where(AgentCredential.key_prefix == prefix)
        )
    ).one_or_none()
    if row is None:
        raise AuthenticationError()
    credential, agent = row
    now = datetime.now(UTC)
    if (
        credential.status != CredentialStatus.ACTIVE
        or agent.status != AgentStatus.ACTIVE
        or (credential.expires_at is not None and credential.expires_at <= now)
        or not agent_key_matches(secret, credential.secret_hash)
    ):
        raise AuthenticationError()
    credential.last_used_at = now
    await session.commit()
    return agent


CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentAgent = Annotated[Agent, Depends(get_current_agent)]
