import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import SecretStr

from app import auth, main
from app.database import get_ingestion_database
from app.json_ingestion import JsonIngestionResult
from app.main import app
from app.official_feeds import DatasetIngestionStatus
from app.raw_ingestion import RawIngestionResult
from app.upstream import get_http_client


def post(path: str, secret: str) -> httpx.Response:
    async def send_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post(
                path,
                headers={"Authorization": f"Bearer {secret}"},
            )

    return asyncio.run(send_request())


def install_dependencies(monkeypatch: pytest.MonkeyPatch) -> str:
    secret = "a" * 32
    monkeypatch.setattr(
        auth,
        "get_settings",
        lambda: SimpleNamespace(cron_secret=SecretStr(secret)),
    )

    async def database_override() -> object:
        return object()

    async def client_override() -> object:
        return object()

    app.dependency_overrides[get_ingestion_database] = database_override
    app.dependency_overrides[get_http_client] = client_override
    return secret


def ingestion_result() -> JsonIngestionResult:
    return JsonIngestionResult(
        changed=True,
        source_updated_at=datetime(2026, 7, 17, 10, tzinfo=UTC),
        fetched_at=datetime(2026, 7, 17, 10, 5, tzinfo=UTC),
    )


def test_all_official_feed_cron_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = install_dependencies(monkeypatch)
    json_result = ingestion_result()
    raw_result = RawIngestionResult(
        changed=True,
        source_updated_at=json_result.source_updated_at,
        fetched_at=json_result.fetched_at,
    )
    batch = [
        DatasetIngestionStatus(
            dataset="batch_item",
            changed=True,
            source_updated_at=json_result.source_updated_at,
            fetched_at=json_result.fetched_at,
        )
    ]

    monkeypatch.setattr(
        main, "ingest_local_forecast", AsyncMock(return_value=json_result)
    )
    monkeypatch.setattr(
        main,
        "ingest_nine_day_forecast",
        AsyncMock(return_value=json_result),
    )
    monkeypatch.setattr(main, "ingest_warnings", AsyncMock(return_value=batch))
    monkeypatch.setattr(
        main,
        "ingest_station_rainfall",
        AsyncMock(return_value=json_result),
    )
    monkeypatch.setattr(
        main,
        "ingest_gridded_rainfall",
        AsyncMock(return_value=raw_result),
    )
    monkeypatch.setattr(
        main,
        "ingest_regional_weather",
        AsyncMock(return_value=batch),
    )
    monkeypatch.setattr(
        main,
        "ingest_smart_lampposts",
        AsyncMock(return_value=batch),
    )

    expected = {
        "/api/cron/local-forecast": "local_forecast",
        "/api/cron/nine-day-forecast": "nine_day_forecast",
        "/api/cron/warnings": "batch_item",
        "/api/cron/station-rainfall": "station_rainfall",
        "/api/cron/rainfall-nowcast": "gridded_rainfall_nowcast",
        "/api/cron/regional-weather": "batch_item",
        "/api/cron/smart-lampposts": "batch_item",
    }

    try:
        for path, dataset in expected.items():
            response = post(path, secret)
            assert response.status_code == 200, response.text
            assert response.headers["cache-control"] == "no-store"
            body = response.json()
            assert body["ok"] is True
            if "datasets" in body:
                assert body["datasets"][0]["dataset"] == dataset
            else:
                assert body["dataset"] == dataset
    finally:
        app.dependency_overrides.clear()
