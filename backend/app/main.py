from __future__ import annotations

from collections.abc import Awaitable, Callable
from uuid import uuid4

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from backend.app.api.router import api_router
from backend.app.core.config import get_settings
from backend.app.core.errors import ApplicationError
from backend.app.core.logging import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    application = FastAPI(
        title="AgentGuard API",
        description="Security, reliability, and observability control plane for AI agents.",
        version="0.7.0",
    )

    @application.exception_handler(ApplicationError)
    async def application_error_handler(_request: Request, exc: ApplicationError) -> JSONResponse:
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
            headers=headers,
        )

    @application.middleware("http")
    async def add_request_id(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        return response

    application.include_router(api_router)
    return application


app = create_app()
