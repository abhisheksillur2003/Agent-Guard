import asyncio
from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from backend.app.core.config import get_settings


class DatabaseUnavailableError(RuntimeError):
    """Raised when PostgreSQL cannot complete the readiness probe."""


@lru_cache
def get_engine() -> AsyncEngine:
    return create_async_engine(
        get_settings().database_url,
        pool_pre_ping=True,
    )


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def check_database() -> None:
    try:
        async with asyncio.timeout(3):
            async with get_engine().connect() as connection:
                await connection.execute(text("SELECT 1"))
    except Exception as exc:
        raise DatabaseUnavailableError("PostgreSQL readiness check failed") from exc
