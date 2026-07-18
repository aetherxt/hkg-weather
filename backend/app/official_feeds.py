import csv
import io
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, ConfigDict, Field, RootModel, TypeAdapter
from pymongo.asynchronous.database import AsyncDatabase

from .json_ingestion import (
    JsonDatasetSpec,
    JsonIngestionResult,
    ingest_json_dataset,
)
from .raw_ingestion import (
    RawDatasetSpec,
    RawIngestionResult,
    ValidatedRawPayload,
    ingest_raw_dataset,
)
from .storage import ArchivePolicy
from .storage_read import (
    DatasetNotFoundError,
    StoredDataError,
    decode_json_object,
    read_latest_document,
)

ARCHIVE_RETENTION = timedelta(days=3)
HONG_KONG = ZoneInfo("Asia/Hong_Kong")
WEATHER_API = "https://data.weather.gov.hk/weatherAPI/opendata/weather.php"

LOCAL_FORECAST_DATASET = "local_forecast"
CURRENT_WEATHER_DATASET = "current_weather"
NINE_DAY_FORECAST_DATASET = "nine_day_forecast"
WARNING_INFORMATION_DATASET = "warning_information"
WARNING_SUMMARY_DATASET = "warning_summary"
SPECIAL_WEATHER_TIPS_DATASET = "special_weather_tips"
STATION_RAINFALL_DATASET = "station_rainfall"
GRIDDED_RAINFALL_NOWCAST_DATASET = "gridded_rainfall_nowcast"
REGIONAL_TEMPERATURE_DATASET = "regional_temperature"
REGIONAL_WIND_DATASET = "regional_wind"
SMART_LAMPPOST_DATASET = "smart_lamppost"
SMART_LAMPPOST_CONFIG_PATH = (
    Path(__file__).parent / "data" / "smart_lamppost_devices.json"
)


def weather_api_url(data_type: str) -> str:
    return f"{WEATHER_API}?{urlencode({'dataType': data_type, 'lang': 'en'})}"


CURRENT_WEATHER_URL = weather_api_url("rhrread")


class CurrentWeatherPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    update_time: datetime = Field(alias="updateTime")


class LocalForecastPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    update_time: datetime = Field(alias="updateTime")


class NineDayForecastPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    weather_forecast: list[dict[str, Any]] = Field(alias="weatherForecast")
    update_time: datetime = Field(alias="updateTime")


class WarningDetail(BaseModel):
    model_config = ConfigDict(extra="allow")

    update_time: datetime = Field(alias="updateTime")


class WarningInformationPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    details: list[WarningDetail] = Field(default_factory=list)


class WarningSummaryItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    update_time: datetime = Field(alias="updateTime")


class WarningSummaryPayload(RootModel[dict[str, WarningSummaryItem]]):
    pass


class SpecialWeatherTip(BaseModel):
    model_config = ConfigDict(extra="allow")

    update_time: datetime = Field(alias="updateTime")


class SpecialWeatherTipsPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    tips: list[SpecialWeatherTip] = Field(alias="swt")


class StationRainfallPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    observation_time: datetime = Field(alias="obsTime")
    hourly_rainfall: list[dict[str, Any]] = Field(alias="hourlyRainfall")


class SmartLamppostObservation(BaseModel):
    model_config = ConfigDict(extra="allow")

    measurement_time: str = Field(alias="TS", pattern=r"^\d{14}$")


class SmartLamppostBody(BaseModel):
    model_config = ConfigDict(extra="allow")

    hko: SmartLamppostObservation = Field(alias="HKO")


class SmartLamppostPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    lamppost_id: str = Field(alias="PI")
    device_id: str = Field(alias="DI")
    body: SmartLamppostBody = Field(alias="BODY")


class CurrentWeatherMetadata(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    dataset: Literal[CURRENT_WEATHER_DATASET] = CURRENT_WEATHER_DATASET
    source_updated_at: datetime = Field(serialization_alias="sourceUpdatedAt")
    fetched_at: datetime = Field(serialization_alias="fetchedAt")


class CurrentWeatherReadResponse(BaseModel):
    data: dict[str, Any]
    meta: CurrentWeatherMetadata


class CurrentWeatherNotFoundError(Exception):
    pass


class StoredCurrentWeatherError(Exception):
    pass


def latest_datetime(values: list[datetime]) -> datetime | None:
    return max(values) if values else None


CURRENT_WEATHER_SPEC = JsonDatasetSpec(
    dataset=CURRENT_WEATHER_DATASET,
    document_id=CURRENT_WEATHER_DATASET,
    url=CURRENT_WEATHER_URL,
    payload_model=CurrentWeatherPayload,
    source_updated_at=lambda payload: payload.update_time,
    archive_retention=ARCHIVE_RETENTION,
)


LOCAL_FORECAST_SPEC = JsonDatasetSpec(
    dataset=LOCAL_FORECAST_DATASET,
    document_id=LOCAL_FORECAST_DATASET,
    url=weather_api_url("flw"),
    payload_model=LocalForecastPayload,
    source_updated_at=lambda payload: payload.update_time,
    archive_retention=ARCHIVE_RETENTION,
)

NINE_DAY_FORECAST_SPEC = JsonDatasetSpec(
    dataset=NINE_DAY_FORECAST_DATASET,
    document_id=NINE_DAY_FORECAST_DATASET,
    url=weather_api_url("fnd"),
    payload_model=NineDayForecastPayload,
    source_updated_at=lambda payload: payload.update_time,
    archive_retention=ARCHIVE_RETENTION,
)

WARNING_INFORMATION_SPEC = JsonDatasetSpec(
    dataset=WARNING_INFORMATION_DATASET,
    document_id=WARNING_INFORMATION_DATASET,
    url=weather_api_url("warningInfo"),
    payload_model=WarningInformationPayload,
    source_updated_at=lambda payload: latest_datetime(
        [detail.update_time for detail in payload.details]
    ),
    archive_retention=None,
)

WARNING_SUMMARY_SPEC = JsonDatasetSpec(
    dataset=WARNING_SUMMARY_DATASET,
    document_id=WARNING_SUMMARY_DATASET,
    url=weather_api_url("warnsum"),
    payload_model=WarningSummaryPayload,
    source_updated_at=lambda payload: latest_datetime(
        [item.update_time for item in payload.root.values()]
    ),
    archive_retention=None,
)

SPECIAL_WEATHER_TIPS_SPEC = JsonDatasetSpec(
    dataset=SPECIAL_WEATHER_TIPS_DATASET,
    document_id=SPECIAL_WEATHER_TIPS_DATASET,
    url=weather_api_url("swt"),
    payload_model=SpecialWeatherTipsPayload,
    source_updated_at=lambda payload: latest_datetime(
        [tip.update_time for tip in payload.tips]
    ),
    archive_retention=None,
)

STATION_RAINFALL_SPEC = JsonDatasetSpec(
    dataset=STATION_RAINFALL_DATASET,
    document_id=STATION_RAINFALL_DATASET,
    url=("https://data.weather.gov.hk/weatherAPI/opendata/hourlyRainfall.php?lang=en"),
    payload_model=StationRainfallPayload,
    source_updated_at=lambda payload: payload.observation_time,
    archive_retention=ARCHIVE_RETENTION,
)


def parse_hong_kong_time(value: str) -> datetime:
    return datetime.strptime(value.strip(), "%Y%m%d%H%M").replace(tzinfo=HONG_KONG)


def validate_regional_csv(
    raw_payload: bytes,
    expected_columns: int,
) -> ValidatedRawPayload:
    reader = csv.reader(io.StringIO(raw_payload.decode("utf-8-sig")))
    header = next(reader, None)
    first_row = next(reader, None)
    if header is None or first_row is None:
        raise ValueError("regional CSV is empty")
    if len(header) != expected_columns or len(first_row) != expected_columns:
        raise ValueError("regional CSV has an unexpected schema")
    source_updated_at = parse_hong_kong_time(first_row[0])
    return ValidatedRawPayload(source_updated_at=source_updated_at)


def validate_temperature_csv(raw_payload: bytes) -> ValidatedRawPayload:
    return validate_regional_csv(raw_payload, expected_columns=3)


def normalize_wind_csv_row(row: list[str]) -> list[str]:
    if len(row) == 5:
        return row
    if (
        len(row) == 6
        and row[2].strip().casefold() == "calm"
        and row[3].strip().casefold() == "calm"
        and not row[5].strip()
    ):
        return [row[0], row[1], row[2], "", row[4]]
    raise ValueError("regional wind CSV row has an unexpected schema")


def validate_wind_csv(raw_payload: bytes) -> ValidatedRawPayload:
    reader = csv.reader(io.StringIO(raw_payload.decode("utf-8-sig")))
    header = next(reader, None)
    if header is None or len(header) != 5:
        raise ValueError("regional wind CSV has an unexpected schema")

    source_updated_at = None
    row_count = 0
    for raw_row in reader:
        if not raw_row:
            continue
        row = normalize_wind_csv_row(raw_row)
        row_updated_at = parse_hong_kong_time(row[0])
        if not row[1].strip():
            raise ValueError("regional wind CSV station is empty")
        source_updated_at = source_updated_at or row_updated_at
        row_count += 1

    if source_updated_at is None or row_count == 0:
        raise ValueError("regional wind CSV is empty")
    return ValidatedRawPayload(source_updated_at=source_updated_at)


def validate_gridded_rainfall_csv(raw_payload: bytes) -> ValidatedRawPayload:
    source = io.StringIO(raw_payload.decode("utf-8-sig"))
    reader = csv.reader(source)
    header = next(reader, None)
    if header is None or len(header) != 5:
        raise ValueError("gridded rainfall CSV has an unexpected schema")

    archive_buffer = io.StringIO(newline="")
    writer = csv.writer(archive_buffer, lineterminator="\n")
    writer.writerow(header)
    selected_valid_times: list[str] = []
    source_updated_at: datetime | None = None
    row_count = 0

    for row in reader:
        if not row:
            continue
        if len(row) != 5:
            raise ValueError("gridded rainfall row has an unexpected schema")
        updated_time, valid_time, latitude, longitude, rainfall = row
        row_updated_at = parse_hong_kong_time(updated_time)
        parse_hong_kong_time(valid_time)
        float(latitude)
        float(longitude)
        float(rainfall)
        source_updated_at = source_updated_at or row_updated_at
        row_count += 1

        if valid_time not in selected_valid_times and len(selected_valid_times) < 2:
            selected_valid_times.append(valid_time)
        if valid_time in selected_valid_times:
            writer.writerow(row)

    if source_updated_at is None or row_count == 0 or len(selected_valid_times) < 2:
        raise ValueError("gridded rainfall CSV contains insufficient data")

    return ValidatedRawPayload(
        source_updated_at=source_updated_at,
        archive_payload=archive_buffer.getvalue().encode(),
        metadata={
            "archive_valid_times": [
                parse_hong_kong_time(value) for value in selected_valid_times
            ]
        },
    )


GRIDDED_RAINFALL_SPEC = RawDatasetSpec(
    dataset=GRIDDED_RAINFALL_NOWCAST_DATASET,
    document_id=GRIDDED_RAINFALL_NOWCAST_DATASET,
    url=(
        "https://data.weather.gov.hk/weatherAPI/hko_data/F3/"
        "Gridded_rainfall_nowcast.csv"
    ),
    validate=validate_gridded_rainfall_csv,
    default_content_type="text/csv",
    archive_retention=ARCHIVE_RETENTION,
    archive_policy=ArchivePolicy.SLOT,
    archive_interval=timedelta(minutes=30),
)

REGIONAL_TEMPERATURE_SPEC = RawDatasetSpec(
    dataset=REGIONAL_TEMPERATURE_DATASET,
    document_id=REGIONAL_TEMPERATURE_DATASET,
    url=(
        "https://data.weather.gov.hk/weatherAPI/hko_data/regional-weather/"
        "latest_1min_temperature.csv"
    ),
    validate=validate_temperature_csv,
    default_content_type="text/csv",
    archive_retention=ARCHIVE_RETENTION,
)

REGIONAL_WIND_SPEC = RawDatasetSpec(
    dataset=REGIONAL_WIND_DATASET,
    document_id=REGIONAL_WIND_DATASET,
    url=(
        "https://data.weather.gov.hk/weatherAPI/hko_data/regional-weather/"
        "latest_10min_wind.csv"
    ),
    validate=validate_wind_csv,
    default_content_type="text/csv",
    archive_retention=ARCHIVE_RETENTION,
)


class SmartLamppostDevice(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    lamppost_id: str = Field(alias="lamppostId", min_length=1, max_length=8)
    device_id: str = Field(alias="deviceId", pattern=r"^\d{2}$")
    label: str = Field(min_length=1)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


@lru_cache
def load_smart_lamppost_devices() -> list[SmartLamppostDevice]:
    return TypeAdapter(list[SmartLamppostDevice]).validate_json(
        SMART_LAMPPOST_CONFIG_PATH.read_bytes()
    )


def smart_lamppost_spec(device: SmartLamppostDevice) -> JsonDatasetSpec:
    query = urlencode({"pi": device.lamppost_id, "di": device.device_id})
    return JsonDatasetSpec(
        dataset=SMART_LAMPPOST_DATASET,
        document_id=(
            f"{SMART_LAMPPOST_DATASET}:{device.lamppost_id}:{device.device_id}"
        ),
        url=(
            "https://data.weather.gov.hk/weatherAPI/smart-lamppost/"
            f"smart-lamppost.php?{query}"
        ),
        payload_model=SmartLamppostPayload,
        source_updated_at=lambda payload: datetime.strptime(
            payload.body.hko.measurement_time,
            "%Y%m%d%H%M%S",
        ).replace(tzinfo=HONG_KONG),
        archive_retention=ARCHIVE_RETENTION,
    )


class DatasetIngestionStatus(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    dataset: str
    changed: bool
    source_updated_at: datetime | None = Field(serialization_alias="sourceUpdatedAt")
    fetched_at: datetime = Field(serialization_alias="fetchedAt")


class DatasetIngestionResponse(DatasetIngestionStatus):
    ok: Literal[True] = True


class BatchIngestionResponse(BaseModel):
    ok: Literal[True] = True
    datasets: list[DatasetIngestionStatus]


class SmartLamppostIngestionResponse(BatchIngestionResponse):
    configured_devices: int = Field(serialization_alias="configuredDevices")


def ingestion_status(
    dataset: str,
    result: JsonIngestionResult | RawIngestionResult,
) -> DatasetIngestionStatus:
    return DatasetIngestionStatus(
        dataset=dataset,
        changed=result.changed,
        source_updated_at=result.source_updated_at,
        fetched_at=result.fetched_at,
    )


async def ingest_local_forecast(
    database: AsyncDatabase,
    client: httpx.AsyncClient,
) -> JsonIngestionResult:
    return await ingest_json_dataset(database, client, LOCAL_FORECAST_SPEC)


async def ingest_current_weather(
    database: AsyncDatabase,
    client: httpx.AsyncClient,
    *,
    now: datetime | None = None,
) -> JsonIngestionResult:
    return await ingest_json_dataset(
        database,
        client,
        CURRENT_WEATHER_SPEC,
        now=now,
    )


async def ingest_nine_day_forecast(
    database: AsyncDatabase,
    client: httpx.AsyncClient,
) -> JsonIngestionResult:
    return await ingest_json_dataset(database, client, NINE_DAY_FORECAST_SPEC)


async def ingest_warnings(
    database: AsyncDatabase,
    client: httpx.AsyncClient,
) -> list[DatasetIngestionStatus]:
    results = []
    for spec in (
        WARNING_SUMMARY_SPEC,
        WARNING_INFORMATION_SPEC,
        SPECIAL_WEATHER_TIPS_SPEC,
    ):
        result = await ingest_json_dataset(database, client, spec)
        results.append(ingestion_status(spec.dataset, result))
    return results


async def ingest_station_rainfall(
    database: AsyncDatabase,
    client: httpx.AsyncClient,
) -> JsonIngestionResult:
    return await ingest_json_dataset(database, client, STATION_RAINFALL_SPEC)


async def ingest_gridded_rainfall(
    database: AsyncDatabase,
    client: httpx.AsyncClient,
) -> RawIngestionResult:
    return await ingest_raw_dataset(database, client, GRIDDED_RAINFALL_SPEC)


async def ingest_regional_weather(
    database: AsyncDatabase,
    client: httpx.AsyncClient,
) -> list[DatasetIngestionStatus]:
    results = []
    for spec in (REGIONAL_TEMPERATURE_SPEC, REGIONAL_WIND_SPEC):
        result = await ingest_raw_dataset(database, client, spec)
        results.append(ingestion_status(spec.dataset, result))
    return results


async def ingest_smart_lampposts(
    database: AsyncDatabase,
    client: httpx.AsyncClient,
    devices: list[SmartLamppostDevice],
) -> list[DatasetIngestionStatus]:
    results = []
    for device in devices:
        spec = smart_lamppost_spec(device)
        result = await ingest_json_dataset(database, client, spec)
        results.append(ingestion_status(spec.document_id, result))
    return results


async def read_current_weather(
    database: AsyncDatabase,
) -> CurrentWeatherReadResponse:
    try:
        document = await read_latest_document(
            database,
            CURRENT_WEATHER_DATASET,
            projection={
                "_id": 0,
                "payload": 1,
                "source_updated_at": 1,
                "fetched_at": 1,
            },
        )
    except DatasetNotFoundError as error:
        raise CurrentWeatherNotFoundError from error

    try:
        payload, stored = decode_json_object(
            document,
            CURRENT_WEATHER_DATASET,
            validate=CurrentWeatherPayload.model_validate,
        )
    except StoredDataError as error:
        raise StoredCurrentWeatherError from error

    return CurrentWeatherReadResponse(
        data=payload,
        meta=CurrentWeatherMetadata(
            source_updated_at=stored.source_updated_at,
            fetched_at=stored.fetched_at,
        ),
    )
