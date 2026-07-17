import asyncio
import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from pymongo.errors import OperationFailure

from app.current_weather import (
    ARCHIVE_RETENTION,
    CURRENT_WEATHER_URL,
    ingest_current_weather,
)
from app.json_ingestion import JsonDatasetStorageError, JsonDatasetUpstreamError


def weather_response(
    payload: dict[str, object],
    status_code: int = 200,
) -> httpx.Response:
    request = httpx.Request("GET", CURRENT_WEATHER_URL)
    return httpx.Response(
        status_code,
        content=json.dumps(payload, separators=(",", ":")).encode(),
        headers={"Content-Type": "application/json; charset=utf-8"},
        request=request,
    )


def database_mock(
    *,
    previous: dict[str, str] | None = None,
) -> tuple[MagicMock, MagicMock, MagicMock]:
    latest = MagicMock()
    latest.find_one = AsyncMock(return_value=previous)
    latest.replace_one = AsyncMock()

    archive = MagicMock()
    archive.create_index = AsyncMock()
    archive.update_one = AsyncMock()

    database = MagicMock()
    database.__getitem__.side_effect = {
        "latest": latest,
        "archive": archive,
    }.__getitem__
    return database, latest, archive


def test_changed_current_weather_is_stored_as_latest_and_archive() -> None:
    payload = {
        "updateTime": "2026-07-17T12:02:00+08:00",
        "icon": [52],
    }
    response = weather_response(payload)
    client = MagicMock()
    client.get = AsyncMock(return_value=response)
    database, latest, archive = database_mock()
    fetched_at = datetime(2026, 7, 17, 4, 10, tzinfo=UTC)

    result = asyncio.run(
        ingest_current_weather(database, client, now=fetched_at)
    )

    expected_hash = sha256(response.content).hexdigest()
    assert result.changed is True
    assert result.fetched_at == fetched_at
    assert result.source_updated_at.isoformat() == "2026-07-17T12:02:00+08:00"
    client.get.assert_awaited_once_with(CURRENT_WEATHER_URL)

    latest_document = latest.replace_one.await_args.args[1]
    assert latest_document["_id"] == "current_weather"
    assert latest_document["payload"] == response.content
    assert latest_document["content_hash"] == expected_hash
    assert latest_document["content_type"] == "application/json"
    assert latest_document["byte_size"] == len(response.content)

    archive_update = archive.update_one.await_args.args[1]["$setOnInsert"]
    assert "_id" not in archive_update
    assert archive_update["payload"] == response.content
    assert archive_update["expires_at"] == fetched_at + ARCHIVE_RETENTION


def test_unchanged_current_weather_refreshes_latest_without_duplicate_archive() -> None:
    payload = {"updateTime": "2026-07-17T12:02:00+08:00"}
    response = weather_response(payload)
    content_hash = sha256(response.content).hexdigest()
    client = MagicMock()
    client.get = AsyncMock(return_value=response)
    database, latest, archive = database_mock(
        previous={"content_hash": content_hash}
    )

    result = asyncio.run(ingest_current_weather(database, client))

    assert result.changed is False
    latest.replace_one.assert_awaited_once()
    archive.update_one.assert_awaited_once()
    assert archive.update_one.await_args.kwargs == {"upsert": True}


def test_invalid_upstream_response_does_not_touch_database() -> None:
    client = MagicMock()
    client.get = AsyncMock(return_value=weather_response({"icon": [52]}))
    database, latest, archive = database_mock()

    with pytest.raises(JsonDatasetUpstreamError) as error:
        asyncio.run(ingest_current_weather(database, client))

    assert type(error.value.__cause__).__name__ == "ValidationError"

    latest.find_one.assert_not_awaited()
    archive.create_index.assert_not_awaited()


def test_database_error_is_not_hidden_by_ingestion_service() -> None:
    client = MagicMock()
    client.get = AsyncMock(
        return_value=weather_response(
            {"updateTime": "2026-07-17T12:02:00+08:00"}
        )
    )
    database, _, archive = database_mock()
    archive.create_index.side_effect = OperationFailure("index failed")

    with pytest.raises(JsonDatasetStorageError) as error:
        asyncio.run(ingest_current_weather(database, client))

    assert isinstance(error.value.__cause__, OperationFailure)

    assert timedelta(days=3) == ARCHIVE_RETENTION
