import asyncio
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from bson import Binary

from app.official_feeds import (
    CurrentWeatherNotFoundError,
    StoredCurrentWeatherError,
    read_current_weather,
)


def database_with_document(document: dict[str, object] | None) -> MagicMock:
    latest = MagicMock()
    latest.find_one = AsyncMock(return_value=document)
    database = MagicMock()
    database.__getitem__.return_value = latest
    return database


def test_read_current_weather_decodes_original_json() -> None:
    payload = {
        "updateTime": "2026-07-17T17:02:00+08:00",
        "icon": [60],
    }
    source_updated_at = datetime(2026, 7, 17, 9, 2, tzinfo=UTC)
    fetched_at = datetime(2026, 7, 17, 9, 19, tzinfo=UTC)
    database = database_with_document(
        {
            "payload": Binary(json.dumps(payload).encode()),
            "source_updated_at": source_updated_at,
            "fetched_at": fetched_at,
        }
    )

    result = asyncio.run(read_current_weather(database))

    assert result.data == payload
    assert result.meta.source_updated_at == source_updated_at
    assert result.meta.fetched_at == fetched_at
    latest = database.__getitem__.return_value
    latest.find_one.assert_awaited_once_with(
        {"_id": "current_weather"},
        {
            "_id": 0,
            "payload": 1,
            "source_updated_at": 1,
            "fetched_at": 1,
        },
    )


def test_read_current_weather_reports_missing_document() -> None:
    database = database_with_document(None)

    with pytest.raises(CurrentWeatherNotFoundError):
        asyncio.run(read_current_weather(database))


@pytest.mark.parametrize(
    "document",
    [
        {
            "payload": Binary(b"not-json"),
            "source_updated_at": datetime(2026, 7, 17, 9, 2, tzinfo=UTC),
            "fetched_at": datetime(2026, 7, 17, 9, 19, tzinfo=UTC),
        },
        {
            "payload": Binary(b"[]"),
            "source_updated_at": datetime(2026, 7, 17, 9, 2, tzinfo=UTC),
            "fetched_at": datetime(2026, 7, 17, 9, 19, tzinfo=UTC),
        },
        {
            "payload": Binary(b"{}"),
            "source_updated_at": datetime(2026, 7, 17, 9, 2, tzinfo=UTC),
            "fetched_at": datetime(2026, 7, 17, 9, 19, tzinfo=UTC),
        },
    ],
)
def test_read_current_weather_rejects_invalid_storage(
    document: dict[str, object],
) -> None:
    database = database_with_document(document)

    with pytest.raises(StoredCurrentWeatherError):
        asyncio.run(read_current_weather(database))
