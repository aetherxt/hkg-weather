import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field
from pymongo.asynchronous.database import AsyncDatabase

from .storage import ensure_storage_indexes

CURRENT_WEATHER_DATASET = "current_weather"
CURRENT_WEATHER_DOCUMENT_ID = "current_weather"
CURRENT_WEATHER_URL = (
    "https://data.weather.gov.hk/weatherAPI/opendata/weather.php"
    "?dataType=rhrread&lang=en"
)
ARCHIVE_RETENTION = timedelta(days=3)


class CurrentWeatherPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    update_time: datetime = Field(alias="updateTime")


class CurrentWeatherIngestionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    ok: Literal[True] = True
    dataset: Literal["current_weather"] = CURRENT_WEATHER_DATASET
    changed: bool
    source_updated_at: datetime = Field(serialization_alias="sourceUpdatedAt")
    fetched_at: datetime = Field(serialization_alias="fetchedAt")


class CurrentWeatherMetadata(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source_updated_at: datetime = Field(serialization_alias="sourceUpdatedAt")
    fetched_at: datetime = Field(serialization_alias="fetchedAt")


class CurrentWeatherReadResponse(BaseModel):
    data: dict[str, Any]
    meta: CurrentWeatherMetadata


class StoredCurrentWeatherDocument(BaseModel):
    payload: bytes
    source_updated_at: datetime
    fetched_at: datetime


class CurrentWeatherNotFoundError(Exception):
    pass


class StoredCurrentWeatherError(Exception):
    pass


@dataclass(frozen=True)
class CurrentWeatherIngestion:
    changed: bool
    source_updated_at: datetime
    fetched_at: datetime


async def ingest_current_weather(
    database: AsyncDatabase,
    client: httpx.AsyncClient,
    *,
    now: datetime | None = None,
) -> CurrentWeatherIngestion:
    response = await client.get(CURRENT_WEATHER_URL)
    response.raise_for_status()

    raw_payload = response.content
    validated_payload = CurrentWeatherPayload.model_validate_json(raw_payload)
    fetched_at = (now or datetime.now(UTC)).astimezone(UTC)
    content_hash = sha256(raw_payload).hexdigest()
    content_type = response.headers.get("content-type", "application/json")
    content_type = content_type.partition(";")[0].strip() or "application/json"

    await ensure_storage_indexes(database)

    latest = database["latest"]
    archive = database["archive"]
    previous = await latest.find_one(
        {"_id": CURRENT_WEATHER_DOCUMENT_ID},
        {"content_hash": 1},
    )
    changed = previous is None or previous.get("content_hash") != content_hash

    document = {
        "_id": CURRENT_WEATHER_DOCUMENT_ID,
        "dataset": CURRENT_WEATHER_DATASET,
        "source_url": CURRENT_WEATHER_URL,
        "content_type": content_type,
        "payload": raw_payload,
        "fetched_at": fetched_at,
        "source_updated_at": validated_payload.update_time,
        "byte_size": len(raw_payload),
        "content_hash": content_hash,
    }
    await latest.replace_one(
        {"_id": CURRENT_WEATHER_DOCUMENT_ID},
        document,
        upsert=True,
    )

    archive_document = {
        key: value for key, value in document.items() if key != "_id"
    }
    archive_document["expires_at"] = fetched_at + ARCHIVE_RETENTION
    await archive.update_one(
        {
            "dataset": CURRENT_WEATHER_DATASET,
            "content_hash": content_hash,
        },
        {"$setOnInsert": archive_document},
        upsert=True,
    )

    return CurrentWeatherIngestion(
        changed=changed,
        source_updated_at=validated_payload.update_time,
        fetched_at=fetched_at,
    )


async def read_current_weather(
    database: AsyncDatabase,
) -> CurrentWeatherReadResponse:
    document = await database["latest"].find_one(
        {"_id": CURRENT_WEATHER_DOCUMENT_ID},
        {
            "_id": 0,
            "payload": 1,
            "source_updated_at": 1,
            "fetched_at": 1,
        },
    )
    if document is None:
        raise CurrentWeatherNotFoundError

    try:
        stored = StoredCurrentWeatherDocument.model_validate(document)
        payload = json.loads(stored.payload)
        if not isinstance(payload, dict):
            raise ValueError("stored current-weather payload must be an object")
        CurrentWeatherPayload.model_validate(payload)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError, ValueError) as error:
        raise StoredCurrentWeatherError from error

    return CurrentWeatherReadResponse(
        data=payload,
        meta=CurrentWeatherMetadata(
            source_updated_at=stored.source_updated_at,
            fetched_at=stored.fetched_at,
        ),
    )
