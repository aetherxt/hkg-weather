import asyncio
import json
import struct
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from bson import Binary
from pymongo.errors import OperationFailure

from app.database import get_read_database
from app.main import app


def request(
    path: str,
    database: object,
    *,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    async def database_override() -> object:
        return database

    async def send_request() -> httpx.Response:
        app.dependency_overrides[get_read_database] = database_override
        try:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                return await client.get(path, headers=headers)
        finally:
            app.dependency_overrides.clear()

    return asyncio.run(send_request())


def database_with_latest(
    document: dict[str, object] | None,
) -> MagicMock:
    latest = MagicMock()
    latest.find_one = AsyncMock(return_value=document)
    database = MagicMock()
    database.__getitem__.return_value = latest
    return database


def json_document(
    payload: dict[str, object],
    *,
    source_updated_at: datetime | None = None,
) -> dict[str, object]:
    return {
        "payload": Binary(json.dumps(payload).encode()),
        "source_updated_at": source_updated_at,
        "fetched_at": datetime(2026, 7, 18, 2, 5, tzinfo=UTC),
        "content_hash": "a" * 64,
        "content_type": "application/json",
        "byte_size": 100,
    }


def test_local_forecast_decodes_json_and_sets_forecast_cache() -> None:
    document = json_document(
        {
            "updateTime": "2026-07-18T10:00:00+08:00",
            "generalSituation": "Fine.",
        },
        source_updated_at=datetime(2026, 7, 18, 2, tzinfo=UTC),
    )

    response = request(
        "/api/weather/forecast/local",
        database_with_latest(document),
    )

    assert response.status_code == 200
    assert response.json()["data"]["generalSituation"] == "Fine."
    assert response.json()["meta"]["dataset"] == "local_forecast"
    assert response.headers["vercel-cdn-cache-control"].startswith("max-age=600")


def test_regional_temperature_returns_typed_missing_values() -> None:
    document = {
        "payload": Binary(
            b"Date time,Automatic Weather Station,Air Temperature(degree Celsius)\n"
            b"202607181000,Chek Lap Kok,27.3\n"
            b"202607181000,Cheung Chau,N/A\n"
        ),
        "source_updated_at": datetime(2026, 7, 18, 2, tzinfo=UTC),
        "fetched_at": datetime(2026, 7, 18, 2, 5, tzinfo=UTC),
    }

    response = request(
        "/api/weather/regional/temperature",
        database_with_latest(document),
    )

    assert response.status_code == 200
    assert response.json()["data"] == [
        {
            "observedAt": "2026-07-18T10:00:00+08:00",
            "station": "Chek Lap Kok",
            "temperatureC": 27.3,
        },
        {
            "observedAt": "2026-07-18T10:00:00+08:00",
            "station": "Cheung Chau",
            "temperatureC": None,
        },
    ]


def test_rainfall_grid_is_north_to_south_and_west_to_east() -> None:
    document = {
        "payload": Binary(
            b"Updated,Valid,Latitude,Longitude,Rainfall\n"
            b"202607181000,202607181030,22.0,114.1,3\n"
            b"202607181000,202607181030,23.0,114.0,1\n"
            b"202607181000,202607181030,22.0,114.0,4\n"
            b"202607181000,202607181030,23.0,114.1,2\n"
        ),
        "source_updated_at": datetime(2026, 7, 18, 2, tzinfo=UTC),
        "fetched_at": datetime(2026, 7, 18, 2, 5, tzinfo=UTC),
    }

    response = request(
        "/api/weather/rainfall/nowcast/202607181030",
        database_with_latest(document),
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "updatedAt": "2026-07-18T10:00:00+08:00",
        "validAt": "2026-07-18T10:30:00+08:00",
        "bounds": {"north": 23.0, "south": 22.0, "east": 114.1, "west": 114.0},
        "width": 2,
        "height": 2,
        "values": [1.0, 2.0, 4.0, 3.0],
    }


def test_radar_image_is_native_png_with_etag_and_conditional_get() -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", 2, 2)
    document = {
        "payload": Binary(png),
        "source_updated_at": datetime(2026, 7, 18, 2, tzinfo=UTC),
        "fetched_at": datetime(2026, 7, 18, 2, 5, tzinfo=UTC),
        "content_hash": "b" * 64,
        "content_type": "image/png",
        "byte_size": len(png),
    }
    database = database_with_latest(document)

    response = request("/api/weather/radar/image", database)
    not_modified = request(
        "/api/weather/radar/image",
        database,
        headers={"If-None-Match": response.headers["etag"]},
    )

    assert response.content == png
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["content-length"] == str(len(png))
    assert response.headers["etag"] == f'"{"b" * 64}"'
    assert not_modified.status_code == 304
    assert not_modified.content == b""


def test_warning_documents_may_all_be_absent() -> None:
    response = request("/api/weather/warnings", database_with_latest(None))

    assert response.status_code == 200
    assert response.json()["data"] == {
        "summary": {},
        "information": {},
        "specialWeatherTips": {},
    }
    assert response.json()["meta"]["sourceUpdatedAt"] is None


@pytest.mark.parametrize(
    "path",
    [
        "/api/weather/lampposts/not-configured/01",
        "/api/weather/models/pangu/rainfall",
        (
            "/api/weather/history/radar?"
            "from=2026-07-10T00:00:00Z&to=2026-07-18T00:00:00Z"
        ),
    ],
)
def test_invalid_reader_parameters_return_uncached_422(path: str) -> None:
    response = request(path, MagicMock())

    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"


def test_database_failures_return_uncached_503() -> None:
    latest = MagicMock()
    latest.find_one = AsyncMock(side_effect=OperationFailure("read failed"))
    database = MagicMock()
    database.__getitem__.return_value = latest

    response = request("/api/weather/forecast/local", database)

    assert response.status_code == 503
    assert response.json() == {"detail": "Weather storage unavailable"}
    assert response.headers["cache-control"] == "no-store"
