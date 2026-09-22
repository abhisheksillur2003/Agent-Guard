from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.app.core.config import get_settings
from backend.app.db.session import DatabaseUnavailableError, check_database

router = APIRouter(tags=["operations"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: Literal["agentguard-api"]
    environment: str


class ReadinessResponse(BaseModel):
    status: Literal["ready"]
    database: Literal["ready"]


@router.get("/healthz", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="agentguard-api",
        environment=get_settings().environment,
    )


@router.get(
    "/readyz",
    response_model=ReadinessResponse,
    responses={503: {"description": "A required dependency is unavailable."}},
)
async def readiness() -> ReadinessResponse | JSONResponse:
    try:
        await check_database()
    except DatabaseUnavailableError:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "database": "unavailable"},
        )
    return ReadinessResponse(status="ready", database="ready")
