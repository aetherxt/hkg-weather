import asyncio
import re
import struct
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo
from functools import lru_cache
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import httpx
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    field_validator,
)
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError

from .ingestion import (
    DatasetStorageError,
    DatasetUpstreamError,
    ValidatedPayload,
    fetch_with_retry,
)
from .json_ingestion import JsonDatasetSpec, ingest_json_dataset
from .official_feeds import (
    BatchIngestionResponse,
    DatasetIngestionStatus,
    ingestion_status,
)
from .raw_ingestion import (
    RawDatasetSpec,
    ingest_raw_dataset,
)
from .storage import ArchivePolicy

ARCHIVE_RETENTION = timedelta(days=3)
HONG_KONG = ZoneInfo("Asia/Hong_Kong")
OCF_ROOT = "https://maps.weather.gov.hk/ocf/dat"
EARTH_WEATHER_ROOT = "https://maps.weather.gov.hk/wxviewer/data"
RADAR_128_INDEX_URL = (
    "https://www.hko.gov.hk/wxinfo/radars/R4_GIS_rad_128/R4_GIS_server_Radar_128.kml"
)
TROPICAL_CYCLONE_INDEX_URL = "https://www.hko.gov.hk/wxinfo/currwx/tc_gis_list.js"
TROPICAL_CYCLONE_TRACK_ROOT = "https://www.hko.gov.hk/wxinfo/currwx/"

OCF_STATION_FORECAST_DATASET = "ocf_station_forecast"
EARTH_WEATHER_CYCLE_DATASET = "earth_weather_model_cycle"
EARTH_WEATHER_RAINFALL_DATASET = "earth_weather_rainfall"
RADAR_128_DATASET = "radar_128"
TROPICAL_CYCLONE_TRACK_DATASET = "tropical_cyclone_track"
OCF_REQUEST_CONCURRENCY = 4
OCF_STATION_CONFIG_PATH = Path(__file__).parent / "data" / "ocf_stations.json"


class OcfDailyForecast(BaseModel):
    model_config = ConfigDict(extra="allow")

    forecast_date: str = Field(alias="ForecastDate", pattern=r"^\d{8}$")
    chance_of_rain: str | None = Field(
        default=None,
        alias="ForecastChanceOfRain",
    )


class OcfHourlyForecast(BaseModel):
    model_config = ConfigDict(extra="allow")

    forecast_hour: str = Field(alias="ForecastHour", pattern=r"^\d{10}$")
    temperature: float | str | None = Field(
        default=None,
        alias="ForecastTemperature",
    )


class OcfStationForecastPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    last_modified: int | str = Field(alias="LastModified")
    station_code: str = Field(
        alias="StationCode",
        pattern=r"^[A-Z0-9]{2,8}$",
    )
    latitude: float = Field(alias="Latitude", ge=-90, le=90)
    longitude: float = Field(alias="Longitude", ge=-180, le=180)
    model_time: int | str = Field(alias="ModelTime")
    daily_forecast: list[OcfDailyForecast] = Field(
        alias="DailyForecast",
        min_length=1,
    )
    hourly_forecast: list[OcfHourlyForecast] = Field(
        alias="HourlyWeatherForecast",
        min_length=1,
    )

    @field_validator("last_modified")
    @classmethod
    def validate_last_modified(cls, value: int | str) -> int | str:
        parse_compact_time(value, "%Y%m%d%H%M%S", HONG_KONG)
        return value

    @field_validator("model_time")
    @classmethod
    def validate_model_time(cls, value: int | str) -> int | str:
        parse_compact_time(value, "%Y%m%d%H", UTC)
        return value


class EarthWeatherCyclePayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    default: str = Field(pattern=r"^\d{10}$")
    tc_track: object | None = None

    @field_validator("default")
    @classmethod
    def validate_default_cycle(cls, value: str) -> str:
        parse_compact_time(value, "%Y%m%d%H", UTC)
        return value


class OcfStation(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    station_code: str = Field(
        alias="stationCode",
        pattern=r"^[A-Z0-9]{2,8}$",
    )
    label: str = Field(min_length=1)


class EarthWeatherModel(BaseModel):
    model_id: str = Field(pattern=r"^[a-z0-9_]+$")
    label: str
    rainfall_interval_hours: int | None = Field(default=None, ge=1)
    maximum_lead_hours: int | None = Field(default=None, ge=1)


class OcfStationIngestionResponse(BatchIngestionResponse):
    configured_stations: int = Field(serialization_alias="configuredStations")


class EarthWeatherCycleIngestionResponse(BatchIngestionResponse):
    configured_models: int = Field(serialization_alias="configuredModels")


class EarthWeatherRainfallIngestionResponse(BatchIngestionResponse):
    configured_models: int = Field(serialization_alias="configuredModels")


class TropicalCycloneIngestionResponse(BatchIngestionResponse):
    active_cyclones: int = Field(serialization_alias="activeCyclones")


@dataclass(frozen=True)
class RadarOverlay:
    image_url: str
    observed_at: datetime
    bounds: dict[str, float]


@dataclass(frozen=True)
class ActiveTropicalCyclone:
    storm_id: str
    english_name: str
    chinese_name: str


EARTH_WEATHER_MODELS = (
    EarthWeatherModel(
        model_id="ec",
        label="ECMWF",
        rainfall_interval_hours=3,
        maximum_lead_hours=360,
    ),
    EarthWeatherModel(
        model_id="aifs",
        label="ECMWF-AIFS",
        rainfall_interval_hours=6,
        maximum_lead_hours=360,
    ),
    EarthWeatherModel(
        model_id="fengwu_ec",
        label="Fengwu",
        rainfall_interval_hours=6,
        maximum_lead_hours=360,
    ),
    EarthWeatherModel(
        model_id="fuxi_ec",
        label="Fuxi",
        rainfall_interval_hours=6,
        maximum_lead_hours=360,
    ),
    EarthWeatherModel(model_id="pangu_ec", label="Pangu"),
    EarthWeatherModel(
        model_id="aamc",
        label="AAMC-WRF",
        rainfall_interval_hours=3,
        maximum_lead_hours=120,
    ),
)

EARTH_WEATHER_RAINFALL_MODELS = tuple(
    model for model in EARTH_WEATHER_MODELS if model.rainfall_interval_hours is not None
)


def parse_compact_time(
    value: int | str,
    date_format: str,
    timezone: tzinfo,
) -> datetime:
    raw_value = str(value)
    try:
        return datetime.strptime(raw_value, date_format).replace(tzinfo=timezone)
    except ValueError as error:
        raise ValueError(f"invalid compact date-time: {raw_value}") from error


def ocf_source_updated_at(payload: OcfStationForecastPayload) -> datetime:
    return parse_compact_time(
        payload.last_modified,
        "%Y%m%d%H%M%S",
        HONG_KONG,
    )


def earth_cycle_source_updated_at(payload: EarthWeatherCyclePayload) -> datetime:
    return parse_compact_time(payload.default, "%Y%m%d%H", UTC)


def format_compact_utc(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%d%H")


def validate_png(
    raw_payload: bytes,
    *,
    source_updated_at: datetime,
    metadata: dict[str, object],
) -> ValidatedPayload:
    if len(raw_payload) < 24 or raw_payload[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("payload is not a PNG")
    if raw_payload[12:16] != b"IHDR":
        raise ValueError("PNG has no IHDR header")
    width, height = struct.unpack(">II", raw_payload[16:24])
    if width == 0 or height == 0:
        raise ValueError("PNG has invalid dimensions")
    return ValidatedPayload(
        source_updated_at=source_updated_at,
        metadata={
            **metadata,
            "raster_width": width,
            "raster_height": height,
        },
    )


def earth_rainfall_lead_hours(
    model: EarthWeatherModel,
    base_time: datetime,
    now: datetime,
) -> int:
    interval = model.rainfall_interval_hours
    maximum = model.maximum_lead_hours
    if interval is None or maximum is None:
        raise ValueError(f"{model.model_id} has no rainfall product")
    elapsed_seconds = max(0, int((now - base_time).total_seconds()))
    interval_seconds = interval * 60 * 60
    next_lead = ((elapsed_seconds // interval_seconds) + 1) * interval
    return min(maximum, next_lead)


def earth_weather_rainfall_spec(
    model: EarthWeatherModel,
    base_time: datetime,
    lead_hours: int,
) -> RawDatasetSpec:
    valid_at = base_time + timedelta(hours=lead_hours)
    base_value = format_compact_utc(base_time)
    valid_value = format_compact_utc(valid_at)
    lead_value = f"{lead_hours:03d}"
    filename = f"{model.model_id}_{base_value}_{valid_value}_f{lead_value}_sfc_RF.png"
    url = f"{EARTH_WEATHER_ROOT}/weather/{model.model_id}/{base_value}/{filename}"
    return RawDatasetSpec(
        dataset=EARTH_WEATHER_RAINFALL_DATASET,
        document_id=f"{EARTH_WEATHER_RAINFALL_DATASET}:{model.model_id}",
        url=url,
        validate=lambda raw_payload: validate_png(
            raw_payload,
            source_updated_at=base_time,
            metadata={
                "model": model.model_id,
                "model_label": model.label,
                "base_time": base_time,
                "valid_at": valid_at,
                "lead_hours": lead_hours,
                "level": "sfc",
                "field": "RF",
            },
        ),
        default_content_type="image/png",
        archive_retention=ARCHIVE_RETENTION,
    )


def _element_text(element: ElementTree.Element, local_name: str) -> str:
    for child in element.iter():
        if child.tag.rpartition("}")[2] == local_name and child.text:
            return child.text.strip()
    raise ValueError(f"missing {local_name}")


def parse_radar_index(raw_payload: bytes) -> RadarOverlay:
    try:
        root = ElementTree.fromstring(raw_payload)
    except ElementTree.ParseError as error:
        raise ValueError("radar index is not valid XML") from error

    overlays: list[RadarOverlay] = []
    for element in root.iter():
        if element.tag.rpartition("}")[2] != "GroundOverlay":
            continue
        href = _element_text(element, "href")
        timestamp = re.search(r"(\d{14})_rad_128\.png$", href)
        if timestamp is None:
            continue
        observed_at = parse_compact_time(
            timestamp.group(1),
            "%Y%m%d%H%M%S",
            HONG_KONG,
        )
        bounds = {
            direction: float(_element_text(element, direction))
            for direction in ("north", "south", "east", "west")
        }
        if bounds["north"] <= bounds["south"]:
            raise ValueError("radar latitude bounds are invalid")
        if bounds["east"] <= bounds["west"]:
            raise ValueError("radar longitude bounds are invalid")
        overlays.append(
            RadarOverlay(
                image_url=urljoin(RADAR_128_INDEX_URL, href),
                observed_at=observed_at,
                bounds=bounds,
            )
        )

    if not overlays:
        raise ValueError("radar index contains no 128 km frames")
    return max(overlays, key=lambda overlay: overlay.observed_at)


def parse_tropical_cyclone_index(
    raw_payload: bytes,
) -> list[ActiveTropicalCyclone]:
    text = raw_payload.decode("utf-8-sig").strip()
    if not text or text.upper() == "NIL":
        return []

    array = re.search(r"\btc\s*=\s*\[(.*?)]\s*;?", text, re.DOTALL)
    indexed_entries = re.findall(
        r"\btc\s*\[\s*(\d+)\s*]\s*=\s*(['\"])(.*?)\2\s*;?",
        text,
        re.DOTALL,
    )
    if array is None and not indexed_entries:
        raise ValueError("tropical-cyclone index has an unexpected format")

    entries = (
        []
        if array is None
        else [
            entry
            for _, entry in re.findall(
                r"(['\"])(.*?)\1",
                array.group(1),
                re.DOTALL,
            )
        ]
    )
    if indexed_entries:
        indexes = [int(index) for index, _, _ in indexed_entries]
        if len(indexes) != len(set(indexes)):
            raise ValueError("tropical-cyclone index contains duplicate entries")
        entries.extend(
            entry
            for _, _, entry in sorted(
                indexed_entries,
                key=lambda indexed_entry: int(indexed_entry[0]),
            )
        )

    if not entries:
        if array is not None and not array.group(1).strip() and "tc[" not in text:
            return []
        raise ValueError("tropical-cyclone index contains no valid entries")

    cyclones = []
    for entry in entries:
        fields = [field.strip() for field in entry.split(",", maxsplit=2)]
        if len(fields) != 3 or not re.fullmatch(r"[A-Za-z0-9_-]+", fields[0]):
            raise ValueError("tropical-cyclone index entry is invalid")
        cyclones.append(
            ActiveTropicalCyclone(
                storm_id=fields[0],
                english_name=fields[1],
                chinese_name=fields[2],
            )
        )
    return cyclones


def validate_tropical_cyclone_track(
    raw_payload: bytes,
    cyclone: ActiveTropicalCyclone,
) -> ValidatedPayload:
    try:
        root = ElementTree.fromstring(raw_payload)
    except ElementTree.ParseError as error:
        raise ValueError("tropical-cyclone track is not valid XML") from error
    if root.tag.rpartition("}")[2].lower() != "kml":
        raise ValueError("tropical-cyclone track is not KML")
    if not any(
        element.tag.rpartition("}")[2] == "coordinates"
        and element.text
        and element.text.strip()
        for element in root.iter()
    ):
        raise ValueError("tropical-cyclone track has no coordinates")
    return ValidatedPayload(
        source_updated_at=None,
        metadata={
            "storm_id": cyclone.storm_id,
            "storm_name_en": cyclone.english_name,
            "storm_name_zh": cyclone.chinese_name,
            "index_url": TROPICAL_CYCLONE_INDEX_URL,
        },
    )


@lru_cache
def load_ocf_stations() -> list[OcfStation]:
    return TypeAdapter(list[OcfStation]).validate_json(
        OCF_STATION_CONFIG_PATH.read_bytes()
    )


def ocf_station_spec(station: OcfStation) -> JsonDatasetSpec:
    station_code = station.station_code.upper()
    return JsonDatasetSpec(
        dataset=OCF_STATION_FORECAST_DATASET,
        document_id=f"{OCF_STATION_FORECAST_DATASET}:{station_code}",
        url=f"{OCF_ROOT}/{station_code}.xml",
        payload_model=OcfStationForecastPayload,
        source_updated_at=ocf_source_updated_at,
        archive_retention=ARCHIVE_RETENTION,
    )


def earth_weather_cycle_spec(model: EarthWeatherModel) -> JsonDatasetSpec:
    return JsonDatasetSpec(
        dataset=EARTH_WEATHER_CYCLE_DATASET,
        document_id=f"{EARTH_WEATHER_CYCLE_DATASET}:{model.model_id}",
        url=f"{EARTH_WEATHER_ROOT}/current_{model.model_id}.json",
        payload_model=EarthWeatherCyclePayload,
        source_updated_at=earth_cycle_source_updated_at,
        archive_retention=None,
    )


async def ingest_ocf_station_forecasts(
    database: AsyncDatabase,
    client: httpx.AsyncClient,
    stations: list[OcfStation],
) -> list[DatasetIngestionStatus]:
    semaphore = asyncio.Semaphore(OCF_REQUEST_CONCURRENCY)

    async def ingest_station(station: OcfStation) -> DatasetIngestionStatus:
        async with semaphore:
            spec = ocf_station_spec(station)
            result = await ingest_json_dataset(database, client, spec)
            return ingestion_status(spec.document_id, result)

    tasks = [asyncio.create_task(ingest_station(station)) for station in stations]
    try:
        return list(await asyncio.gather(*tasks))
    except Exception:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


async def ingest_earth_weather_cycles(
    database: AsyncDatabase,
    client: httpx.AsyncClient,
    models: tuple[EarthWeatherModel, ...] = EARTH_WEATHER_MODELS,
) -> list[DatasetIngestionStatus]:
    results = []
    for model in models:
        spec = earth_weather_cycle_spec(model)
        result = await ingest_json_dataset(
            database,
            client,
            spec,
        )
        results.append(ingestion_status(spec.document_id, result))
    return results


async def _fetch_earth_weather_cycle(
    client: httpx.AsyncClient,
    model: EarthWeatherModel,
) -> EarthWeatherCyclePayload:
    spec = earth_weather_cycle_spec(model)
    try:
        response = await client.get(spec.url)
        response.raise_for_status()
        return EarthWeatherCyclePayload.model_validate_json(response.content)
    except (httpx.HTTPError, ValueError) as error:
        raise DatasetUpstreamError(spec.dataset) from error


async def ingest_earth_weather_rainfall(
    database: AsyncDatabase,
    client: httpx.AsyncClient,
    models: tuple[EarthWeatherModel, ...] = EARTH_WEATHER_RAINFALL_MODELS,
    *,
    now: datetime | None = None,
) -> list[DatasetIngestionStatus]:
    current_time = (now or datetime.now(UTC)).astimezone(UTC)
    results = []
    for model in models:
        cycle = await _fetch_earth_weather_cycle(client, model)
        try:
            base_time = earth_cycle_source_updated_at(cycle)
        except ValueError as error:
            raise DatasetUpstreamError(EARTH_WEATHER_CYCLE_DATASET) from error
        lead_hours = earth_rainfall_lead_hours(
            model,
            base_time,
            current_time,
        )
        spec = earth_weather_rainfall_spec(model, base_time, lead_hours)
        result = await ingest_raw_dataset(
            database,
            client,
            spec,
            now=current_time,
        )
        results.append(ingestion_status(spec.document_id, result))
    return results


async def ingest_radar_128(
    database: AsyncDatabase,
    client: httpx.AsyncClient,
) -> DatasetIngestionStatus:
    try:
        response = await client.get(RADAR_128_INDEX_URL)
        response.raise_for_status()
        overlay = parse_radar_index(response.content)
    except (httpx.HTTPError, UnicodeError, ValueError) as error:
        raise DatasetUpstreamError(RADAR_128_DATASET) from error

    spec = RawDatasetSpec(
        dataset=RADAR_128_DATASET,
        document_id=RADAR_128_DATASET,
        url=overlay.image_url,
        validate=lambda raw_payload: validate_png(
            raw_payload,
            source_updated_at=overlay.observed_at,
            metadata={
                "observed_at": overlay.observed_at,
                "bounds": overlay.bounds,
                "index_url": RADAR_128_INDEX_URL,
            },
        ),
        default_content_type="image/png",
        archive_retention=ARCHIVE_RETENTION,
        archive_policy=ArchivePolicy.SLOT,
        archive_interval=timedelta(minutes=30),
    )
    result = await ingest_raw_dataset(database, client, spec)
    return ingestion_status(spec.document_id, result)


async def ingest_tropical_cyclone_tracks(
    database: AsyncDatabase,
    client: httpx.AsyncClient,
) -> list[DatasetIngestionStatus]:
    try:
        response = await fetch_with_retry(
            client,
            TROPICAL_CYCLONE_INDEX_URL,
            TROPICAL_CYCLONE_TRACK_DATASET,
        )
        cyclones = parse_tropical_cyclone_index(response.content)
    except DatasetUpstreamError:
        raise
    except (httpx.HTTPError, UnicodeError, ValueError) as error:
        raise DatasetUpstreamError(TROPICAL_CYCLONE_TRACK_DATASET) from error

    results = []
    for cyclone in cyclones:
        url = urljoin(
            TROPICAL_CYCLONE_TRACK_ROOT,
            f"tc_gis_track_15a_e_{cyclone.storm_id}.xml",
        )
        spec = RawDatasetSpec(
            dataset=TROPICAL_CYCLONE_TRACK_DATASET,
            document_id=(f"{TROPICAL_CYCLONE_TRACK_DATASET}:{cyclone.storm_id}"),
            url=url,
            validate=lambda raw_payload, cyclone=cyclone: (
                validate_tropical_cyclone_track(raw_payload, cyclone)
            ),
            default_content_type="application/vnd.google-earth.kml+xml",
            archive_retention=ARCHIVE_RETENTION,
        )
        result = await ingest_raw_dataset(database, client, spec)
        results.append(ingestion_status(spec.document_id, result))

    active_document_ids = [result.dataset for result in results]
    try:
        await database["latest"].delete_many(
            {
                "dataset": TROPICAL_CYCLONE_TRACK_DATASET,
                "_id": {"$nin": active_document_ids},
            }
        )
    except PyMongoError as error:
        raise DatasetStorageError(TROPICAL_CYCLONE_TRACK_DATASET) from error
    return results
