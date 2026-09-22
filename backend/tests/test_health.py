import httpx
from pytest import MonkeyPatch

from backend.app.api.routes import health as health_routes
from backend.app.db.session import DatabaseUnavailableError
from backend.app.main import app


async def test_healthz_reports_process_health() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "agentguard-api",
        "environment": "local",
    }
    assert response.headers["x-request-id"]


async def test_request_id_is_preserved() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz", headers={"x-request-id": "request-test-123"})

    assert response.headers["x-request-id"] == "request-test-123"


async def test_readyz_reports_ready_database(monkeypatch: MonkeyPatch) -> None:
    async def database_is_ready() -> None:
        return None

    monkeypatch.setattr(health_routes, "check_database", database_is_ready)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/readyz")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ready"}


async def test_readyz_fails_closed_when_database_is_unavailable(
    monkeypatch: MonkeyPatch,
) -> None:
    async def database_is_unavailable() -> None:
        raise DatabaseUnavailableError("database unavailable")

    monkeypatch.setattr(health_routes, "check_database", database_is_unavailable)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/readyz")

    assert response.status_code == 503
    assert response.json() == {"status": "not_ready", "database": "unavailable"}
