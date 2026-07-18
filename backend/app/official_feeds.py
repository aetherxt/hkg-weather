import csv
import io
import math
from collections.abc import Callable
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import httpx
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    TypeAdapter,
    field_validator,
)
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
TEMPERATURE_MISSING_VALUES = frozenset({"", "N/A", "M", "////"})
WIND_SPEED_MISSING_VALUES = frozenset({"", "N/A", "M", "////"})
WIND_GUST_MISSING_VALUES = frozenset({"", "N/A", "M", "////"})
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

    @field_validator("measurement_time")
    @classmethod
    def validate_measurement_time(cls, value: str) -> str:
        datetime.strptime(value, "%Y%m%d%H%M%S")
        return value


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


def _validate_numeric_or_missing(
    value: str,
    field: str,
    missing_values: frozenset[str],
) -> None:
    cleaned = value.strip()
    if cleaned.upper() in missing_values:
        return
    try:
        number = float(cleaned)
    except ValueError as error:
        raise ValueError(f"regional CSV {field} is not numeric") from error
    if not math.isfinite(number):
        raise ValueError(f"regional CSV {field} is not finite")


def validate_regional_observations(
    raw_payload: bytes,
    *,
    expected_columns: int,
    measurement_columns: tuple[tuple[int, str, frozenset[str]], ...],
    normalize_row: Callable[[list[str]], list[str]] | None = None,
) -> ValidatedRawPayload:
    reader = csv.reader(
        io.StringIO(raw_payload.decode("utf-8-sig")),
        strict=True,
    )
    try:
        header = next(reader, None)
        if header is None or len(header) != expected_columns:
            raise ValueError("regional CSV has an unexpected schema")

        source_updated_at = None
        row_count = 0
        for raw_row in reader:
            if not raw_row or all(not value.strip() for value in raw_row):
                continue
            row = normalize_row(raw_row) if normalize_row else raw_row
            if len(row) != expected_columns:
                raise ValueError("regional CSV row has an unexpected schema")

            row_updated_at = parse_hong_kong_time(row[0])
            if source_updated_at is None:
                source_updated_at = row_updated_at
            elif row_updated_at != source_updated_at:
                raise ValueError("regional CSV has inconsistent observation times")

            if not row[1].strip():
                raise ValueError("regional CSV station is empty")
            for column, field, missing_values in measurement_columns:
                _validate_numeric_or_missing(
                    row[column],
                    field,
                    missing_values,
                )
            row_count += 1
    except csv.Error as error:
        raise ValueError("regional CSV is malformed") from error

    if source_updated_at is None or row_count == 0:
        raise ValueError("regional CSV is empty")
    return ValidatedRawPayload(source_updated_at=source_updated_at)


def validate_temperature_csv(raw_payload: bytes) -> ValidatedRawPayload:
    return validate_regional_observations(
        raw_payload,
        expected_columns=3,
        measurement_columns=((2, "temperature", TEMPERATURE_MISSING_VALUES),),
    )


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
    return validate_regional_observations(
        raw_payload,
        expected_columns=5,
        measurement_columns=(
            (3, "wind speed", WIND_SPEED_MISSING_VALUES),
            (4, "maximum gust", WIND_GUST_MISSING_VALUES),
        ),
        normalize_row=normalize_wind_csv_row,
    )


def validate_gridded_rainfall_csv(raw_payload: bytes) -> ValidatedRawPayload:
    source = io.StringIO(raw_payload.decode("utf-8-sig"))
    reader = csv.reader(source, strict=True)
    source_updated_at: datetime | None = None
    valid_time_order: list[datetime] = []
    rows_by_valid_time: dict[datetime, list[list[str]]] = {}
    coordinates_by_valid_time: dict[datetime, set[tuple[float, float]]] = {}
    current_valid_time: datetime | None = None

    try:
        header = next(reader, None)
        if header is None or len(header) != 5:
            raise ValueError("gridded rainfall CSV has an unexpected schema")

        for row in reader:
            if not row or all(not value.strip() for value in row):
                continue
            if len(row) != 5:
                raise ValueError("gridded rainfall row has an unexpected schema")

            updated_time, valid_time, raw_latitude, raw_longitude, raw_rainfall = row
            row_updated_at = parse_hong_kong_time(updated_time)
            row_valid_at = parse_hong_kong_time(valid_time)
            try:
                latitude = float(raw_latitude)
                longitude = float(raw_longitude)
                rainfall = float(raw_rainfall)
            except ValueError as error:
                raise ValueError(
                    "gridded rainfall row contains a non-numeric value"
                ) from error
            if not all(
                math.isfinite(value)
                for value in (latitude, longitude, rainfall)
            ):
                raise ValueError("gridded rainfall row contains a non-finite value")
            if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                raise ValueError("gridded rainfall coordinate is out of range")

            if source_updated_at is None:
                source_updated_at = row_updated_at
            elif row_updated_at != source_updated_at:
                raise ValueError("gridded rainfall has inconsistent issue times")
            if row_valid_at <= row_updated_at:
                raise ValueError("gridded rainfall valid time is not in the future")

            if row_valid_at != current_valid_time:
                if row_valid_at in rows_by_valid_time:
                    raise ValueError(
                        "gridded rainfall forecast periods are not contiguous"
                    )
                if valid_time_order and row_valid_at <= valid_time_order[-1]:
                    raise ValueError(
                        "gridded rainfall forecast periods are not chronological"
                    )
                valid_time_order.append(row_valid_at)
                rows_by_valid_time[row_valid_at] = []
                coordinates_by_valid_time[row_valid_at] = set()
                current_valid_time = row_valid_at

            coordinate = (latitude, longitude)
            coordinates = coordinates_by_valid_time[row_valid_at]
            if coordinate in coordinates:
                raise ValueError("gridded rainfall grid has duplicate coordinates")
            coordinates.add(coordinate)
            rows_by_valid_time[row_valid_at].append(row)
    except csv.Error as error:
        raise ValueError("gridded rainfall CSV is malformed") from error

    if source_updated_at is None or len(valid_time_order) < 2:
        raise ValueError("gridded rainfall CSV contains insufficient data")

    reference_coordinates: set[tuple[float, float]] | None = None
    for valid_time in valid_time_order:
        coordinates = coordinates_by_valid_time[valid_time]
        latitudes = {latitude for latitude, _ in coordinates}
        longitudes = {longitude for _, longitude in coordinates}
        if len(coordinates) != len(latitudes) * len(longitudes):
            raise ValueError("gridded rainfall grid is not rectangular")
        if reference_coordinates is None:
            reference_coordinates = coordinates
        elif coordinates != reference_coordinates:
            raise ValueError("gridded rainfall forecast grids are inconsistent")

    selected_valid_times = sorted(valid_time_order)[:2]
    archive_buffer = io.StringIO(newline="")
    writer = csv.writer(archive_buffer, lineterminator="\n")
    writer.writerow(header)
    for valid_time in selected_valid_times:
        writer.writerows(rows_by_valid_time[valid_time])

    return ValidatedRawPayload(
        source_updated_at=source_updated_at,
        archive_payload=archive_buffer.getvalue().encode(),
        metadata={
            "archive_valid_times": selected_valid_times,
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
