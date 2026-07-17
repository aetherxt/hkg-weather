import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field
from pymongo.asynchronous.database import AsyncDatabase

from .json_ingestion import JsonDatasetSpec, ingest_json_dataset

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


CURRENT_WEATHER_SPEC = JsonDatasetSpec(
    dataset=CURRENT_WEATHER_DATASET,
    document_id=CURRENT_WEATHER_DOCUMENT_ID,
    url=CURRENT_WEATHER_URL,
    payload_model=CurrentWeatherPayload,
    source_updated_at=lambda payload: payload.update_time,
    archive_retention=ARCHIVE_RETENTION,
)


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
    result = await ingest_json_dataset(
        database,
        client,
        CURRENT_WEATHER_SPEC,
        now=now,
    )
    if result.source_updated_at is None:
        raise RuntimeError("current weather must have an update time")

    return CurrentWeatherIngestion(
        changed=result.changed,
        source_updated_at=result.source_updated_at,
        fetched_at=result.fetched_at,
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
