from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from uuid import uuid4

import httpx
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from backend.app.core.config import get_settings
from backend.app.db.base import Base
from backend.app.db.session import get_session
from backend.app.main import app
from backend.app.models import Organization, User
from backend.app.services.authentication import bootstrap_admin


@dataclass
class ApiContext:
    client: httpx.AsyncClient
    session: AsyncSession
    organization: Organization
    admin: User
    admin_headers: dict[str, str]


@pytest_asyncio.fixture
async def api_context() -> AsyncIterator[ApiContext]:
    schema = f"test_{uuid4().hex}"
    database_url = get_settings().database_url
    admin_engine = create_async_engine(database_url)
    async with admin_engine.begin() as connection:
        await connection.execute(CreateSchema(schema))

    test_engine = create_async_engine(
        database_url,
        connect_args={"server_settings": {"search_path": schema}},
    )
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with factory() as session:

        async def override_session() -> AsyncIterator[AsyncSession]:
            yield session

        app.dependency_overrides[get_session] = override_session
        organization, admin = await bootstrap_admin(
            session,
            organization_name="AgentGuard Test",
            organization_slug="agentguard-test",
            email="admin@example.com",
            password="CorrectHorseBattery1!",
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            token_response = await client.post(
                "/api/v1/auth/token",
                data={"username": admin.email, "password": "CorrectHorseBattery1!"},
            )
            assert token_response.status_code == 200
            token = token_response.json()["access_token"]
            yield ApiContext(
                client=client,
                session=session,
                organization=organization,
                admin=admin,
                admin_headers={"Authorization": f"Bearer {token}"},
            )

    app.dependency_overrides.clear()
    await test_engine.dispose()
    async with admin_engine.begin() as connection:
        await connection.execute(DropSchema(schema, cascade=True))
    await admin_engine.dispose()
