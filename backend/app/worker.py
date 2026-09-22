import asyncio
from typing import Any

from celery import Celery  # pyright: ignore[reportMissingTypeStubs]

from backend.app.core.config import get_settings
from backend.app.db.session import get_engine, get_session_factory
from backend.app.services.reliability_jobs import (
    expire_due_approvals,
    reconcile_stale_executions,
)

settings = get_settings()
celery_app: Any = Celery("agentguard", broker=settings.redis_url)
celery_app.conf.update(
    broker_connection_retry_on_startup=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_ignore_result=True,
    beat_schedule={
        "expire-due-approvals": {
            "task": "agentguard.expire_due_approvals",
            "schedule": 60.0,
        },
        "reconcile-stale-executions": {
            "task": "agentguard.reconcile_stale_executions",
            "schedule": 60.0,
        },
    },
)


async def _expire_due_approvals() -> int:
    engine = get_engine()
    try:
        async with get_session_factory()() as session:
            return await expire_due_approvals(session)
    finally:
        await engine.dispose()
        get_session_factory.cache_clear()
        get_engine.cache_clear()


async def _reconcile_stale_executions() -> int:
    engine = get_engine()
    try:
        async with get_session_factory()() as session:
            return await reconcile_stale_executions(session, settings.stale_execution_seconds)
    finally:
        await engine.dispose()
        get_session_factory.cache_clear()
        get_engine.cache_clear()


def expire_due_approvals_task() -> int:
    return asyncio.run(_expire_due_approvals())


def reconcile_stale_executions_task() -> int:
    return asyncio.run(_reconcile_stale_executions())


celery_app.task(name="agentguard.expire_due_approvals")(expire_due_approvals_task)
celery_app.task(name="agentguard.reconcile_stale_executions")(reconcile_stale_executions_task)
