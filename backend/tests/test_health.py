import asyncio

import httpx
import pytest

from app.main import app


def test_application_health() -> None:
    async def request_health() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get("/api/health")

    response = asyncio.run(request_health())

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("vercel_environment", ["preview", "production"])
def test_database_health_is_hidden_on_vercel(
    monkeypatch: pytest.MonkeyPatch,
    vercel_environment: str,
) -> None:
    monkeypatch.setenv("VERCEL_ENV", vercel_environment)

    async def request_health() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get("/api/health/database")

    response = asyncio.run(request_health())

    assert response.status_code == 404
    assert response.headers["cache-control"] == "no-store"
