import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import SecretStr
from pymongo.errors import OperationFailure

from app import auth, main
from app.current_weather import CurrentWeatherIngestion
from app.database import get_ingestion_database
from app.main import app
from app.upstream import get_http_client


def request_current_weather(
    authorization: str | None = None,
) -> httpx.Response:
    async def send_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        headers = {"Authorization": authorization} if authorization else {}
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post(
                "/api/cron/current-weather",
                headers=headers,
            )

    return asyncio.run(send_request())


def install_secret(monkeypatch: pytest.MonkeyPatch) -> str:
    secret = "a" * 32
    settings = SimpleNamespace(cron_secret=SecretStr(secret))
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    return secret


def install_dependencies() -> None:
    async def database_override() -> object:
        return object()

    async def client_override() -> object:
        return object()

    app.dependency_overrides[get_ingestion_database] = database_override
    app.dependency_overrides[get_http_client] = client_override


def test_route_requires_cron_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    install_secret(monkeypatch)

    response = request_current_weather()

    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}
    assert response.headers["cache-control"] == "no-store"


def test_route_ingests_current_weather(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = install_secret(monkeypatch)
    install_dependencies()
    ingestion = AsyncMock(
        return_value=CurrentWeatherIngestion(
            changed=True,
            source_updated_at=datetime.fromisoformat(
                "2026-07-17T12:02:00+08:00"
            ),
            fetched_at=datetime(2026, 7, 17, 4, 10, tzinfo=UTC),
        )
    )
    monkeypatch.setattr(main, "ingest_current_weather", ingestion)

    try:
        response = request_current_weather(f"Bearer {secret}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["ok"] is True
    assert response.json()["dataset"] == "current_weather"
    assert response.json()["changed"] is True
    assert response.json()["sourceUpdatedAt"] == "2026-07-17T12:02:00+08:00"
    ingestion.assert_awaited_once()


def test_route_reports_upstream_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = install_secret(monkeypatch)
    install_dependencies()
    request = httpx.Request("GET", "https://example.test/weather")
    upstream_error = httpx.HTTPStatusError(
        "upstream unavailable",
        request=request,
        response=httpx.Response(503, request=request),
    )
    monkeypatch.setattr(
        main,
        "ingest_current_weather",
        AsyncMock(side_effect=upstream_error),
    )

    try:
        response = request_current_weather(f"Bearer {secret}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502
    assert response.json() == {"detail": "Upstream weather data unavailable"}
    assert response.headers["cache-control"] == "no-store"


def test_route_reports_database_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = install_secret(monkeypatch)
    install_dependencies()
    monkeypatch.setattr(
        main,
        "ingest_current_weather",
        AsyncMock(side_effect=OperationFailure("write failed")),
    )

    try:
        response = request_current_weather(f"Bearer {secret}")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {"detail": "Weather storage unavailable"}
    assert response.headers["cache-control"] == "no-store"
