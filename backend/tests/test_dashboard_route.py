import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

from fastapi import Response

import app.weather_latest_reads as latest_reads
from app.storage_read import DatasetNotFoundError, StoredDataError
from app.weather_read_models import (
    AstronomicalTimes,
    DataResponse,
    LamppostReading,
    ListResponse,
    ListResponseMetadata,
    ResponseMetadata,
    TemperatureReading,
    WarningsData,
    WindReading,
)

NOW = datetime(2026, 7, 23, 6, tzinfo=UTC)


def metadata(dataset: str) -> ResponseMetadata:
    return ResponseMetadata(
        dataset=dataset,
        source_updated_at=NOW,
        fetched_at=NOW,
    )


def list_metadata(dataset: str, count: int) -> ListResponseMetadata:
    return ListResponseMetadata(
        **metadata(dataset).model_dump(),
        count=count,
    )


def patch_dashboard_sections(monkeypatch) -> None:
    monkeypatch.setattr(
        latest_reads,
        "get_warnings",
        AsyncMock(
            return_value=DataResponse(
                data=WarningsData(
                    summary={},
                    information={},
                    special_weather_tips={},
                ),
                meta=metadata("warnings"),
            )
        ),
    )
    for name, dataset in (
        ("get_current_weather", "current_weather"),
        ("get_local_forecast", "local_forecast"),
        ("get_nine_day_forecast", "nine_day_forecast"),
        ("get_station_rainfall", "station_rainfall"),
    ):
        monkeypatch.setattr(
            latest_reads,
            name,
            AsyncMock(return_value=DataResponse(data={}, meta=metadata(dataset))),
        )
    monkeypatch.setattr(
        latest_reads,
        "get_regional_temperature",
        AsyncMock(
            return_value=ListResponse[TemperatureReading](
                data=[],
                meta=list_metadata("regional_temperature", 0),
            )
        ),
    )
    monkeypatch.setattr(
        latest_reads,
        "get_regional_wind",
        AsyncMock(
            return_value=ListResponse[WindReading](
                data=[],
                meta=list_metadata("regional_wind", 0),
            )
        ),
    )
    monkeypatch.setattr(
        latest_reads,
        "get_lampposts",
        AsyncMock(
            return_value=ListResponse[LamppostReading](
                data=[],
                meta=list_metadata("smart_lamppost", 0),
            )
        ),
    )
    monkeypatch.setattr(
        latest_reads,
        "get_sun",
        AsyncMock(
            return_value=DataResponse(
                data=AstronomicalTimes(
                    date="2026-07-23",
                    sunrise="05:51",
                    sun_transit="12:29",
                    sunset="19:07",
                    moonrise=None,
                    moon_transit=None,
                    moonset=None,
                ),
                meta=metadata("sunrise_sunset"),
            )
        ),
    )


def test_dashboard_combines_sections_and_sets_five_minute_cache(monkeypatch) -> None:
    patch_dashboard_sections(monkeypatch)
    response = Response()

    result = asyncio.run(latest_reads.get_dashboard(response, MagicMock()))

    assert result.data.current is not None
    assert result.data.astronomical is not None
    assert result.meta.dataset == "dashboard"
    assert response.headers["vercel-cdn-cache-control"] == (
        "max-age=300, stale-while-revalidate=600"
    )


def test_dashboard_keeps_other_sections_when_one_is_missing(monkeypatch) -> None:
    patch_dashboard_sections(monkeypatch)
    monkeypatch.setattr(
        latest_reads,
        "get_current_weather",
        AsyncMock(side_effect=DatasetNotFoundError("current_weather")),
    )

    result = asyncio.run(latest_reads.get_dashboard(Response(), MagicMock()))

    assert result.data.current is None
    assert result.data.warnings is not None
    assert result.data.local_forecast is not None


def test_dashboard_fails_when_every_section_is_missing(monkeypatch) -> None:
    for name in (
        "get_warnings",
        "get_current_weather",
        "get_local_forecast",
        "get_nine_day_forecast",
        "get_regional_temperature",
        "get_regional_wind",
        "get_lampposts",
        "get_sun",
        "get_station_rainfall",
    ):
        monkeypatch.setattr(
            latest_reads,
            name,
            AsyncMock(side_effect=DatasetNotFoundError(name)),
        )

    try:
        asyncio.run(latest_reads.get_dashboard(Response(), MagicMock()))
    except StoredDataError as error:
        assert error.dataset == "dashboard"
    else:
        raise AssertionError("an empty dashboard should be unavailable")
