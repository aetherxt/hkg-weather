import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import httpx
import pytest
from pymongo.errors import OperationFailure

from app import main
from app.database import get_read_database
from app.main import app
from app.official_feeds import (
    CurrentWeatherMetadata,
    CurrentWeatherNotFoundError,
    CurrentWeatherReadResponse,
    StoredCurrentWeatherError,
)


def request_current_weather() -> httpx.Response:
    async def send_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get("/api/weather/current")

    return asyncio.run(send_request())


def install_reader_dependency() -> None:
    async def database_override() -> object:
        return object()

    app.dependency_overrides[get_read_database] = database_override


def test_current_weather_route_returns_public_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_reader_dependency()
    read_service = AsyncMock(
        return_value=CurrentWeatherReadResponse(
            data={
                "updateTime": "2026-07-17T17:02:00+08:00",
                "icon": [60],
            },
            meta=CurrentWeatherMetadata(
                source_updated_at=datetime(2026, 7, 17, 9, 2, tzinfo=UTC),
                fetched_at=datetime(2026, 7, 17, 9, 19, tzinfo=UTC),
            ),
        )
    )
    monkeypatch.setattr(main, "read_current_weather", read_service)

    try:
        response = request_current_weather()
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["data"]["icon"] == [60]
    assert response.json()["meta"] == {
        "dataset": "current_weather",
        "sourceUpdatedAt": "2026-07-17T09:02:00Z",
        "fetchedAt": "2026-07-17T09:19:00Z",
    }
    assert response.headers["cache-control"] == (
        "public, max-age=0, must-revalidate"
    )
    assert response.headers["vercel-cdn-cache-control"] == (
        "max-age=300, stale-while-revalidate=600"
    )
    read_service.assert_awaited_once()


@pytest.mark.parametrize(
    ("error", "status_code", "detail"),
    [
        (CurrentWeatherNotFoundError(), 404, "Current weather not found"),
        (StoredCurrentWeatherError(), 503, "Weather data unavailable"),
        (OperationFailure("read failed"), 503, "Weather storage unavailable"),
    ],
)
def test_current_weather_route_errors_are_not_cached(
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
    status_code: int,
    detail: str,
) -> None:
    install_reader_dependency()
    monkeypatch.setattr(
        main,
        "read_current_weather",
        AsyncMock(side_effect=error),
    )

    try:
        response = request_current_weather()
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == status_code
    assert response.json() == {"detail": detail}
    assert response.headers["cache-control"] == "no-store"
    assert "vercel-cdn-cache-control" not in response.headers
