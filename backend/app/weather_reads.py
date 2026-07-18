import hashlib
import re
import xml.etree.ElementTree as ElementTree
from collections import defaultdict
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from pymongo import ASCENDING
from pymongo.asynchronous.database import AsyncDatabase

from .database import get_read_database
from .internal_feeds import (
    EARTH_WEATHER_CYCLE_DATASET,
    EARTH_WEATHER_MODELS,
    EARTH_WEATHER_RAINFALL_DATASET,
    EARTH_WEATHER_RAINFALL_MODELS,
    OCF_STATION_FORECAST_DATASET,
    RADAR_128_DATASET,
    TROPICAL_CYCLONE_TRACK_DATASET,
    EarthWeatherCyclePayload,
    OcfStationForecastPayload,
    load_ocf_stations,
)
from .official_feeds import (
    GRIDDED_RAINFALL_NOWCAST_DATASET,
    LOCAL_FORECAST_DATASET,
    NINE_DAY_FORECAST_DATASET,
    REGIONAL_TEMPERATURE_DATASET,
    REGIONAL_WIND_DATASET,
    SMART_LAMPPOST_DATASET,
    SPECIAL_WEATHER_TIPS_DATASET,
    STATION_RAINFALL_DATASET,
    WARNING_INFORMATION_DATASET,
    WARNING_SUMMARY_DATASET,
    LocalForecastPayload,
    NineDayForecastPayload,
    SmartLamppostPayload,
    SpecialWeatherTipsPayload,
    StationRainfallPayload,
    WarningInformationPayload,
    WarningSummaryPayload,
    load_smart_lamppost_devices,
    normalize_wind_csv_row,
    parse_hong_kong_time,
)
from .storage_read import (
    LATEST_PROJECTION,
    DatasetNotFoundError,
    StoredDataError,
    StoredDocument,
    StoredMetadata,
    decode_csv_rows,
    decode_json_object,
    read_binary_payload,
    read_latest_document,
    validate_stored_document,
    validate_stored_metadata,
)

HONG_KONG = ZoneInfo("Asia/Hong_Kong")
MAX_ARCHIVE_RANGE = timedelta(days=3)
MAX_ARCHIVE_RESULTS = 512
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

LATEST_BROWSER_CACHE = "public, max-age=0, must-revalidate"
FAST_CDN_CACHE = "max-age=60, stale-while-revalidate=300"
FORECAST_CDN_CACHE = "max-age=600, stale-while-revalidate=1200"
IMMUTABLE_CACHE = "public, max-age=31536000, immutable"

ReadDatabase = Annotated[AsyncDatabase, Depends(get_read_database)]


class PublicModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
    )


class ErrorResponse(PublicModel):
    detail: str | list[dict[str, Any]]


router = APIRouter(
    prefix="/api/weather",
    tags=["weather"],
    responses={
        404: {"model": ErrorResponse, "description": "Stored data not found"},
        422: {"model": ErrorResponse, "description": "Invalid parameters"},
        503: {"model": ErrorResponse, "description": "Weather data unavailable"},
    },
)


class ResponseMetadata(PublicModel):
    dataset: str
    source_updated_at: datetime | None
    fetched_at: datetime | None


class ListResponseMetadata(ResponseMetadata):
    count: int


class DataResponse[Data](PublicModel):
    data: Data
    meta: ResponseMetadata


class ListResponse[Item](PublicModel):
    data: list[Item]
    meta: ListResponseMetadata


class WarningsData(PublicModel):
    summary: dict[str, Any]
    information: dict[str, Any]
    special_weather_tips: dict[str, Any]


class TemperatureReading(PublicModel):
    observed_at: datetime
    station: str
    temperature_c: float | None


class WindReading(PublicModel):
    observed_at: datetime
    station: str
    mean_wind_direction: str | None
    mean_wind_speed_kmh: float | None
    maximum_gust_kmh: float | None


class LamppostReading(PublicModel):
    lamppost_id: str
    device_id: str
    label: str
    latitude: float
    longitude: float
    reading: dict[str, Any]


class StationItem(PublicModel):
    station_code: str
    label: str


class ModelItem(PublicModel):
    model_id: str
    label: str
    rainfall_interval_hours: int | None
    maximum_lead_hours: int | None
    current_cycle: datetime | None
    cycle_fetched_at: datetime | None


class Bounds(PublicModel):
    north: float
    south: float
    east: float
    west: float


class RainfallGrid(PublicModel):
    updated_at: datetime
    valid_at: datetime
    bounds: Bounds
    width: int
    height: int
    values: list[float | None]


class RainfallFrame(PublicModel):
    updated_at: datetime
    valid_at: datetime
    bounds: Bounds
    width: int
    height: int
    url: str


class RadarMetadata(PublicModel):
    observed_at: datetime
    bounds: Bounds
    width: int
    height: int
    image_url: str


class ModelRainfallMetadata(PublicModel):
    model_id: str
    label: str
    cycle: datetime
    lead_hours: int
    valid_at: datetime
    width: int
    height: int
    image_url: str


class TropicalCyclone(PublicModel):
    storm_id: str
    name_en: str
    name_zh: str
    geo_json: dict[str, Any]


class ArchivedObservation(PublicModel):
    source_updated_at: datetime | None
    fetched_at: datetime
    observation: dict[str, Any]


class ArchivedRainfallFrame(PublicModel):
    issue_time: datetime
    valid_time: datetime
    url: str


class ArchivedRadarFrame(PublicModel):
    observed_at: datetime
    bounds: Bounds
    width: int
    height: int
    image_url: str


class ArchivedForecast(PublicModel):
    source_updated_at: datetime | None
    fetched_at: datetime
    forecast: dict[str, Any]


class ArchivedModelRainfall(PublicModel):
    cycle: datetime
    valid_at: datetime
    lead_hours: int
    width: int
    height: int
    image_url: str


def _meta(
    dataset: str,
    stored: StoredMetadata | None,
) -> ResponseMetadata:
    return ResponseMetadata(
        dataset=dataset,
        source_updated_at=(stored.source_updated_at if stored else None),
        fetched_at=(stored.fetched_at if stored else None),
    )


def _list_meta(
    dataset: str,
    documents: list[StoredMetadata],
    count: int,
) -> ListResponseMetadata:
    source_times = [
        item.source_updated_at
        for item in documents
        if item.source_updated_at is not None
    ]
    fetched_times = [item.fetched_at for item in documents]
    return ListResponseMetadata(
        dataset=dataset,
        source_updated_at=max(source_times) if source_times else None,
        fetched_at=max(fetched_times) if fetched_times else None,
        count=count,
    )


def _set_latest_cache(response: Response, *, forecast: bool = False) -> None:
    response.headers["Cache-Control"] = LATEST_BROWSER_CACHE
    response.headers["Vercel-CDN-Cache-Control"] = (
        FORECAST_CDN_CACHE if forecast else FAST_CDN_CACHE
    )


def _error(status_code: int, detail: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=detail,
        headers={"Cache-Control": "no-store"},
    )


def _public_keys(value: Any) -> Any:
    if isinstance(value, list):
        return [_public_keys(item) for item in value]
    if not isinstance(value, dict):
        return value

    normalized = {}
    for key, item in value.items():
        if "_" in key:
            public_key = to_camel(key)
        elif key.isupper():
            public_key = key.lower()
        else:
            public_key = key[:1].lower() + key[1:]
        normalized[public_key] = _public_keys(item)
    return normalized


def _number_or_none(value: str) -> float | None:
    cleaned = value.strip()
    if not cleaned or cleaned.upper() in {"N/A", "M", "////", "CALM"}:
        return None
    try:
        return float(cleaned)
    except ValueError as error:
        raise ValueError("measurement is not numeric") from error


def _content_hash(payload: bytes, stored: StoredDocument) -> str:
    return stored.content_hash or hashlib.sha256(payload).hexdigest()


def _etag(payload: bytes, stored: StoredDocument) -> str:
    return f'"{_content_hash(payload, stored)}"'


def _image_response(
    request: Request,
    payload: bytes,
    stored: StoredDocument,
    *,
    immutable: bool,
) -> Response:
    etag = _etag(payload, stored)
    headers = {
        "Cache-Control": IMMUTABLE_CACHE if immutable else LATEST_BROWSER_CACHE,
        "ETag": etag,
        "Content-Length": str(len(payload)),
    }
    if not immutable:
        headers["Vercel-CDN-Cache-Control"] = FAST_CDN_CACHE
    if request.headers.get("if-none-match") == etag:
        headers.pop("Content-Length")
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    return Response(content=payload, media_type="image/png", headers=headers)


def _parse_public_time(value: str, default_timezone: tzinfo = UTC) -> datetime:
    try:
        if re.fullmatch(r"\d{12}", value):
            return datetime.strptime(value, "%Y%m%d%H%M").replace(
                tzinfo=default_timezone
            )
        if re.fullmatch(r"\d{8}T\d{6}Z", value):
            return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=default_timezone)
        return parsed
    except ValueError as error:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Invalid timestamp",
        ) from error


def _compact_hong_kong(value: datetime) -> str:
    return value.astimezone(HONG_KONG).strftime("%Y%m%d%H%M")


def _compact_utc(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _validate_range(
    from_time: datetime,
    to_time: datetime,
) -> tuple[datetime, datetime]:
    start = from_time.replace(tzinfo=UTC) if from_time.tzinfo is None else from_time
    end = to_time.replace(tzinfo=UTC) if to_time.tzinfo is None else to_time
    start = start.astimezone(UTC)
    end = end.astimezone(UTC)
    if end < start:
        raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "to must not precede from")
    if end - start > MAX_ARCHIVE_RANGE:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Archive range must not exceed three days",
        )
    return start, end


async def _archive_documents(
    database: AsyncDatabase,
    dataset: str,
    field: str,
    from_time: datetime,
    to_time: datetime,
    *,
    extra_filter: dict[str, Any] | None = None,
    projection: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    start, end = _validate_range(from_time, to_time)
    query: dict[str, Any] = {
        "dataset": dataset,
        field: {"$gte": start, "$lte": end},
    }
    if extra_filter:
        query.update(extra_filter)
    cursor = database["archive"].find(query, projection or LATEST_PROJECTION)
    cursor = cursor.sort(field, ASCENDING).limit(MAX_ARCHIVE_RESULTS + 1)
    documents = await cursor.to_list(length=MAX_ARCHIVE_RESULTS + 1)
    if len(documents) > MAX_ARCHIVE_RESULTS:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Archive query contains too many results",
        )
    return documents


def _parse_rainfall_grids(
    document: dict[str, Any],
) -> tuple[list[RainfallGrid], StoredDocument]:
    rows, stored = decode_csv_rows(
        document,
        GRIDDED_RAINFALL_NOWCAST_DATASET,
        expected_columns=5,
    )
    grouped: dict[tuple[datetime, datetime], dict[tuple[float, float], float]] = (
        defaultdict(dict)
    )
    try:
        for updated, valid, raw_latitude, raw_longitude, raw_rainfall in rows:
            key = (parse_hong_kong_time(updated), parse_hong_kong_time(valid))
            coordinate = (float(raw_latitude), float(raw_longitude))
            if coordinate in grouped[key]:
                raise ValueError("rainfall grid contains duplicate coordinates")
            grouped[key][coordinate] = float(raw_rainfall)

        grids = []
        for (updated_at, valid_at), points in sorted(grouped.items()):
            latitudes = sorted({point[0] for point in points}, reverse=True)
            longitudes = sorted({point[1] for point in points})
            if len(points) != len(latitudes) * len(longitudes):
                raise ValueError("rainfall grid is not rectangular")
            grids.append(
                RainfallGrid(
                    updated_at=updated_at,
                    valid_at=valid_at,
                    bounds=Bounds(
                        north=max(latitudes),
                        south=min(latitudes),
                        east=max(longitudes),
                        west=min(longitudes),
                    ),
                    width=len(longitudes),
                    height=len(latitudes),
                    values=[
                        points[(latitude, longitude)]
                        for latitude in latitudes
                        for longitude in longitudes
                    ],
                )
            )
    except ValueError as error:
        raise StoredDataError(GRIDDED_RAINFALL_NOWCAST_DATASET) from error
    if not grids:
        raise StoredDataError(GRIDDED_RAINFALL_NOWCAST_DATASET)
    return grids, stored


def _bounds(document: dict[str, Any], dataset: str) -> Bounds:
    try:
        bounds = Bounds.model_validate(document["bounds"])
        if bounds.north <= bounds.south or bounds.east <= bounds.west:
            raise ValueError("invalid bounds")
        return bounds
    except (KeyError, TypeError, ValueError) as error:
        raise StoredDataError(dataset) from error


def _positive_int(document: dict[str, Any], key: str, dataset: str) -> int:
    value = document.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise StoredDataError(dataset)
    return value


def _document_datetime(
    document: dict[str, Any],
    key: str,
    dataset: str,
) -> datetime:
    value = document.get(key)
    if not isinstance(value, datetime):
        raise StoredDataError(dataset)
    return value


def _tropical_cyclone_geo_json(payload: bytes) -> dict[str, Any]:
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as error:
        raise StoredDataError(TROPICAL_CYCLONE_TRACK_DATASET) from error

    features = []
    for placemark in root.iter():
        if placemark.tag.rpartition("}")[2] != "Placemark":
            continue
        properties: dict[str, Any] = {}
        for child in placemark:
            local_name = child.tag.rpartition("}")[2]
            if local_name in {"name", "description"} and child.text:
                properties[local_name] = child.text.strip()
        for element in placemark.iter():
            geometry_type = element.tag.rpartition("}")[2]
            if geometry_type not in {"Point", "LineString", "LinearRing"}:
                continue
            coordinate_element = next(
                (
                    child
                    for child in element.iter()
                    if child.tag.rpartition("}")[2] == "coordinates" and child.text
                ),
                None,
            )
            if coordinate_element is None:
                continue
            coordinates = []
            try:
                for token in coordinate_element.text.split():
                    values = [float(item) for item in token.split(",")]
                    if len(values) < 2:
                        raise ValueError("coordinate has too few values")
                    coordinates.append(values[:3])
            except ValueError as error:
                raise StoredDataError(TROPICAL_CYCLONE_TRACK_DATASET) from error
            if not coordinates:
                continue
            geo_type = "Point" if geometry_type == "Point" else "LineString"
            features.append(
                {
                    "type": "Feature",
                    "properties": properties,
                    "geometry": {
                        "type": geo_type,
                        "coordinates": (
                            coordinates[0] if geo_type == "Point" else coordinates
                        ),
                    },
                }
            )
    if not features:
        for element in root.iter():
            if element.tag.rpartition("}")[2] != "coordinates" or not element.text:
                continue
            try:
                coordinates = []
                for token in element.text.split():
                    values = [float(item) for item in token.split(",")]
                    if len(values) < 2:
                        raise ValueError("coordinate has too few values")
                    coordinates.append(values[:3])
            except ValueError as error:
                raise StoredDataError(TROPICAL_CYCLONE_TRACK_DATASET) from error
            if coordinates:
                features.append(
                    {
                        "type": "Feature",
                        "properties": {},
                        "geometry": {
                            "type": "Point" if len(coordinates) == 1 else "LineString",
                            "coordinates": (
                                coordinates[0] if len(coordinates) == 1 else coordinates
                            ),
                        },
                    }
                )
    if not features:
        raise StoredDataError(TROPICAL_CYCLONE_TRACK_DATASET)
    return {"type": "FeatureCollection", "features": features}


@router.get(
    "/forecast/local",
    response_model=DataResponse[dict[str, Any]],
)
async def get_local_forecast(
    response: Response,
    database: ReadDatabase,
) -> DataResponse[dict[str, Any]]:
    document = await read_latest_document(database, LOCAL_FORECAST_DATASET)
    payload, stored = decode_json_object(
        document,
        LOCAL_FORECAST_DATASET,
        validate=LocalForecastPayload.model_validate,
    )
    _set_latest_cache(response, forecast=True)
    return DataResponse(data=payload, meta=_meta(LOCAL_FORECAST_DATASET, stored))


@router.get(
    "/forecast/nine-day",
    response_model=DataResponse[dict[str, Any]],
)
async def get_nine_day_forecast(
    response: Response,
    database: ReadDatabase,
) -> DataResponse[dict[str, Any]]:
    document = await read_latest_document(database, NINE_DAY_FORECAST_DATASET)
    payload, stored = decode_json_object(
        document,
        NINE_DAY_FORECAST_DATASET,
        validate=NineDayForecastPayload.model_validate,
    )
    _set_latest_cache(response, forecast=True)
    return DataResponse(data=payload, meta=_meta(NINE_DAY_FORECAST_DATASET, stored))


@router.get(
    "/warnings",
    response_model=DataResponse[WarningsData],
)
async def get_warnings(
    response: Response,
    database: ReadDatabase,
) -> DataResponse[WarningsData]:
    specifications = (
        (WARNING_SUMMARY_DATASET, WarningSummaryPayload.model_validate),
        (WARNING_INFORMATION_DATASET, WarningInformationPayload.model_validate),
        (SPECIAL_WEATHER_TIPS_DATASET, SpecialWeatherTipsPayload.model_validate),
    )
    payloads: list[dict[str, Any]] = []
    documents: list[StoredDocument] = []
    for dataset, validator in specifications:
        try:
            document = await read_latest_document(database, dataset)
        except DatasetNotFoundError:
            payloads.append({})
            continue
        payload, stored = decode_json_object(
            document,
            dataset,
            validate=validator,
        )
        payloads.append(payload)
        documents.append(stored)

    _set_latest_cache(response)
    list_meta = _list_meta("warnings", documents, len(documents))
    return DataResponse(
        data=WarningsData(
            summary=payloads[0],
            information=payloads[1],
            special_weather_tips=payloads[2],
        ),
        meta=ResponseMetadata(
            dataset="warnings",
            source_updated_at=list_meta.source_updated_at,
            fetched_at=list_meta.fetched_at,
        ),
    )


@router.get(
    "/rainfall/stations",
    response_model=DataResponse[dict[str, Any]],
)
async def get_station_rainfall(
    response: Response,
    database: ReadDatabase,
) -> DataResponse[dict[str, Any]]:
    document = await read_latest_document(database, STATION_RAINFALL_DATASET)
    payload, stored = decode_json_object(
        document,
        STATION_RAINFALL_DATASET,
        validate=StationRainfallPayload.model_validate,
    )
    _set_latest_cache(response)
    return DataResponse(data=payload, meta=_meta(STATION_RAINFALL_DATASET, stored))


@router.get(
    "/regional/temperature",
    response_model=ListResponse[TemperatureReading],
)
async def get_regional_temperature(
    response: Response,
    database: ReadDatabase,
) -> ListResponse[TemperatureReading]:
    document = await read_latest_document(database, REGIONAL_TEMPERATURE_DATASET)
    rows, stored = decode_csv_rows(
        document,
        REGIONAL_TEMPERATURE_DATASET,
        expected_columns=3,
    )
    try:
        readings = [
            TemperatureReading(
                observed_at=parse_hong_kong_time(row[0]),
                station=row[1].strip(),
                temperature_c=_number_or_none(row[2]),
            )
            for row in rows
        ]
        if any(not item.station for item in readings):
            raise ValueError("station is empty")
    except ValueError as error:
        raise StoredDataError(REGIONAL_TEMPERATURE_DATASET) from error
    _set_latest_cache(response)
    return ListResponse(
        data=readings,
        meta=ListResponseMetadata(
            **_meta(REGIONAL_TEMPERATURE_DATASET, stored).model_dump(),
            count=len(readings),
        ),
    )


@router.get(
    "/regional/wind",
    response_model=ListResponse[WindReading],
)
async def get_regional_wind(
    response: Response,
    database: ReadDatabase,
) -> ListResponse[WindReading]:
    document = await read_latest_document(database, REGIONAL_WIND_DATASET)
    rows, stored = decode_csv_rows(
        document,
        REGIONAL_WIND_DATASET,
        expected_columns=5,
        normalize_row=normalize_wind_csv_row,
    )
    try:
        readings = [
            WindReading(
                observed_at=parse_hong_kong_time(row[0]),
                station=row[1].strip(),
                mean_wind_direction=(
                    None
                    if not row[2].strip() or row[2].strip().upper() == "N/A"
                    else row[2].strip()
                ),
                mean_wind_speed_kmh=_number_or_none(row[3]),
                maximum_gust_kmh=_number_or_none(row[4]),
            )
            for row in rows
        ]
        if any(not item.station for item in readings):
            raise ValueError("station is empty")
    except ValueError as error:
        raise StoredDataError(REGIONAL_WIND_DATASET) from error
    _set_latest_cache(response)
    return ListResponse(
        data=readings,
        meta=ListResponseMetadata(
            **_meta(REGIONAL_WIND_DATASET, stored).model_dump(),
            count=len(readings),
        ),
    )


async def _lamppost_reading(
    database: AsyncDatabase,
    lamppost_id: str,
    device_id: str,
) -> tuple[LamppostReading, StoredDocument]:
    device = next(
        (
            item
            for item in load_smart_lamppost_devices()
            if item.lamppost_id == lamppost_id and item.device_id == device_id
        ),
        None,
    )
    if device is None:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Unsupported lamppost device",
        )
    document_id = f"{SMART_LAMPPOST_DATASET}:{lamppost_id}:{device_id}"
    document = await read_latest_document(database, document_id)
    payload, stored = decode_json_object(
        document,
        document_id,
        validate=SmartLamppostPayload.model_validate,
    )
    return (
        LamppostReading(
            lamppost_id=device.lamppost_id,
            device_id=device.device_id,
            label=device.label,
            latitude=device.latitude,
            longitude=device.longitude,
            reading=_public_keys(payload),
        ),
        stored,
    )


@router.get(
    "/lampposts",
    response_model=ListResponse[LamppostReading],
)
async def get_lampposts(
    response: Response,
    database: ReadDatabase,
) -> ListResponse[LamppostReading]:
    readings = []
    documents = []
    for device in load_smart_lamppost_devices():
        try:
            reading, stored = await _lamppost_reading(
                database,
                device.lamppost_id,
                device.device_id,
            )
        except DatasetNotFoundError:
            continue
        readings.append(reading)
        documents.append(stored)
    if not readings:
        raise DatasetNotFoundError(SMART_LAMPPOST_DATASET)
    _set_latest_cache(response)
    return ListResponse(
        data=readings,
        meta=_list_meta(SMART_LAMPPOST_DATASET, documents, len(readings)),
    )


@router.get(
    "/lampposts/{lamppost_id}/{device_id}",
    response_model=DataResponse[LamppostReading],
)
async def get_lamppost(
    lamppost_id: str,
    device_id: str,
    response: Response,
    database: ReadDatabase,
) -> DataResponse[LamppostReading]:
    reading, stored = await _lamppost_reading(database, lamppost_id, device_id)
    _set_latest_cache(response)
    return DataResponse(
        data=reading,
        meta=_meta(
            f"{SMART_LAMPPOST_DATASET}:{lamppost_id}:{device_id}",
            stored,
        ),
    )


@router.get(
    "/stations",
    response_model=ListResponse[StationItem],
)
async def get_stations(response: Response) -> ListResponse[StationItem]:
    stations = [
        StationItem(station_code=item.station_code, label=item.label)
        for item in load_ocf_stations()
    ]
    _set_latest_cache(response, forecast=True)
    return ListResponse(
        data=stations,
        meta=ListResponseMetadata(
            dataset="ocf_stations",
            source_updated_at=None,
            fetched_at=None,
            count=len(stations),
        ),
    )


def _configured_station(station_code: str) -> StationItem:
    normalized = station_code.upper()
    station = next(
        (item for item in load_ocf_stations() if item.station_code == normalized),
        None,
    )
    if station is None:
        raise _error(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unsupported station code")
    return StationItem(station_code=station.station_code, label=station.label)


@router.get(
    "/stations/{station_code}/forecast",
    response_model=DataResponse[dict[str, Any]],
)
async def get_station_forecast(
    station_code: str,
    response: Response,
    database: ReadDatabase,
) -> DataResponse[dict[str, Any]]:
    station = _configured_station(station_code)
    document_id = f"{OCF_STATION_FORECAST_DATASET}:{station.station_code}"
    document = await read_latest_document(database, document_id)
    payload, stored = decode_json_object(
        document,
        document_id,
        validate=OcfStationForecastPayload.model_validate,
    )
    public_payload = _public_keys(payload)
    public_payload["stationLabel"] = station.label
    _set_latest_cache(response, forecast=True)
    return DataResponse(data=public_payload, meta=_meta(document_id, stored))


@router.get(
    "/models",
    response_model=ListResponse[ModelItem],
)
async def get_models(
    response: Response,
    database: ReadDatabase,
) -> ListResponse[ModelItem]:
    models = []
    documents = []
    for model in EARTH_WEATHER_MODELS:
        document_id = f"{EARTH_WEATHER_CYCLE_DATASET}:{model.model_id}"
        cycle = None
        cycle_fetched_at = None
        try:
            document = await read_latest_document(database, document_id)
        except DatasetNotFoundError:
            pass
        else:
            payload, stored = decode_json_object(
                document,
                document_id,
                validate=EarthWeatherCyclePayload.model_validate,
            )
            try:
                cycle = datetime.strptime(payload["default"], "%Y%m%d%H").replace(
                    tzinfo=UTC
                )
            except (KeyError, TypeError, ValueError) as error:
                raise StoredDataError(document_id) from error
            cycle_fetched_at = stored.fetched_at
            documents.append(stored)
        models.append(
            ModelItem(
                model_id=model.model_id,
                label=model.label,
                rainfall_interval_hours=model.rainfall_interval_hours,
                maximum_lead_hours=model.maximum_lead_hours,
                current_cycle=cycle,
                cycle_fetched_at=cycle_fetched_at,
            )
        )
    _set_latest_cache(response)
    return ListResponse(
        data=models,
        meta=_list_meta(EARTH_WEATHER_CYCLE_DATASET, documents, len(models)),
    )


@router.get(
    "/tropical-cyclones",
    response_model=ListResponse[TropicalCyclone],
)
async def get_tropical_cyclones(
    response: Response,
    database: ReadDatabase,
) -> ListResponse[TropicalCyclone]:
    cursor = (
        database["latest"]
        .find(
            {"dataset": TROPICAL_CYCLONE_TRACK_DATASET},
            LATEST_PROJECTION,
        )
        .limit(20)
    )
    raw_documents = await cursor.to_list(length=20)
    cyclones = []
    documents = []
    for document in raw_documents:
        stored = validate_stored_document(document, TROPICAL_CYCLONE_TRACK_DATASET)
        try:
            storm_id = str(document["storm_id"])
            name_en = str(document["storm_name_en"])
            name_zh = str(document["storm_name_zh"])
        except KeyError as error:
            raise StoredDataError(TROPICAL_CYCLONE_TRACK_DATASET) from error
        if not storm_id or not name_en:
            raise StoredDataError(TROPICAL_CYCLONE_TRACK_DATASET)
        cyclones.append(
            TropicalCyclone(
                storm_id=storm_id,
                name_en=name_en,
                name_zh=name_zh,
                geo_json=_tropical_cyclone_geo_json(stored.payload),
            )
        )
        documents.append(stored)
    cyclones.sort(key=lambda item: item.storm_id)
    _set_latest_cache(response)
    return ListResponse(
        data=cyclones,
        meta=_list_meta(
            TROPICAL_CYCLONE_TRACK_DATASET,
            documents,
            len(cyclones),
        ),
    )


@router.get(
    "/rainfall/nowcast",
    response_model=ListResponse[RainfallFrame],
)
async def get_rainfall_nowcast_index(
    response: Response,
    database: ReadDatabase,
) -> ListResponse[RainfallFrame]:
    document = await read_latest_document(database, GRIDDED_RAINFALL_NOWCAST_DATASET)
    grids, stored = _parse_rainfall_grids(document)
    frames = [
        RainfallFrame(
            updated_at=grid.updated_at,
            valid_at=grid.valid_at,
            bounds=grid.bounds,
            width=grid.width,
            height=grid.height,
            url=(f"/api/weather/rainfall/nowcast/{_compact_hong_kong(grid.valid_at)}"),
        )
        for grid in grids
    ]
    _set_latest_cache(response)
    return ListResponse(
        data=frames,
        meta=ListResponseMetadata(
            **_meta(GRIDDED_RAINFALL_NOWCAST_DATASET, stored).model_dump(),
            count=len(frames),
        ),
    )


@router.get(
    "/rainfall/nowcast/{valid_time}",
    response_model=DataResponse[RainfallGrid],
)
async def get_rainfall_nowcast_grid(
    valid_time: str,
    response: Response,
    database: ReadDatabase,
) -> DataResponse[RainfallGrid]:
    requested_time = _parse_public_time(valid_time, HONG_KONG)
    document = await read_latest_document(database, GRIDDED_RAINFALL_NOWCAST_DATASET)
    grids, stored = _parse_rainfall_grids(document)
    grid = next(
        (
            item
            for item in grids
            if item.valid_at.astimezone(UTC) == requested_time.astimezone(UTC)
        ),
        None,
    )
    if grid is None:
        raise DatasetNotFoundError(f"{GRIDDED_RAINFALL_NOWCAST_DATASET}:{valid_time}")
    _set_latest_cache(response)
    return DataResponse(
        data=grid,
        meta=_meta(GRIDDED_RAINFALL_NOWCAST_DATASET, stored),
    )


@router.get(
    "/radar",
    response_model=DataResponse[RadarMetadata],
)
async def get_radar_metadata(
    response: Response,
    database: ReadDatabase,
) -> DataResponse[RadarMetadata]:
    document = await read_latest_document(database, RADAR_128_DATASET)
    stored = validate_stored_document(document, RADAR_128_DATASET)
    data = RadarMetadata(
        observed_at=_document_datetime(document, "observed_at", RADAR_128_DATASET),
        bounds=_bounds(document, RADAR_128_DATASET),
        width=_positive_int(document, "raster_width", RADAR_128_DATASET),
        height=_positive_int(document, "raster_height", RADAR_128_DATASET),
        image_url="/api/weather/radar/image",
    )
    _set_latest_cache(response)
    return DataResponse(data=data, meta=_meta(RADAR_128_DATASET, stored))


@router.get(
    "/radar/image",
    response_class=Response,
    responses={
        200: {"content": {"image/png": {}}},
        304: {"description": "Not modified"},
    },
)
async def get_radar_image(
    request: Request,
    database: ReadDatabase,
) -> Response:
    document = await read_latest_document(database, RADAR_128_DATASET)
    payload, stored = read_binary_payload(
        document,
        RADAR_128_DATASET,
        expected_content_type="image/png",
        signature=PNG_SIGNATURE,
    )
    return _image_response(request, payload, stored, immutable=False)


def _rainfall_model(model_id: str):
    model = next(
        (item for item in EARTH_WEATHER_RAINFALL_MODELS if item.model_id == model_id),
        None,
    )
    if model is None:
        raise _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Unsupported rainfall model",
        )
    return model


def _model_rainfall_metadata(
    document: dict[str, Any],
    model_id: str,
    *,
    image_url: str,
) -> ModelRainfallMetadata:
    model = _rainfall_model(model_id)
    if document.get("model") != model.model_id:
        raise StoredDataError(f"{EARTH_WEATHER_RAINFALL_DATASET}:{model_id}")
    lead_hours = _positive_int(
        document,
        "lead_hours",
        EARTH_WEATHER_RAINFALL_DATASET,
    )
    return ModelRainfallMetadata(
        model_id=model.model_id,
        label=model.label,
        cycle=_document_datetime(
            document,
            "base_time",
            EARTH_WEATHER_RAINFALL_DATASET,
        ),
        lead_hours=lead_hours,
        valid_at=_document_datetime(
            document,
            "valid_at",
            EARTH_WEATHER_RAINFALL_DATASET,
        ),
        width=_positive_int(
            document,
            "raster_width",
            EARTH_WEATHER_RAINFALL_DATASET,
        ),
        height=_positive_int(
            document,
            "raster_height",
            EARTH_WEATHER_RAINFALL_DATASET,
        ),
        image_url=image_url,
    )


@router.get(
    "/models/{model_id}/rainfall",
    response_model=DataResponse[ModelRainfallMetadata],
)
async def get_model_rainfall_metadata(
    model_id: str,
    response: Response,
    database: ReadDatabase,
) -> DataResponse[ModelRainfallMetadata]:
    model = _rainfall_model(model_id)
    document_id = f"{EARTH_WEATHER_RAINFALL_DATASET}:{model.model_id}"
    document = await read_latest_document(database, document_id)
    stored = validate_stored_document(document, document_id)
    data = _model_rainfall_metadata(
        document,
        model.model_id,
        image_url=f"/api/weather/models/{model.model_id}/rainfall/image",
    )
    _set_latest_cache(response)
    return DataResponse(data=data, meta=_meta(document_id, stored))


@router.get(
    "/models/{model_id}/rainfall/image",
    response_class=Response,
    responses={
        200: {"content": {"image/png": {}}},
        304: {"description": "Not modified"},
    },
)
async def get_model_rainfall_image(
    model_id: str,
    request: Request,
    database: ReadDatabase,
) -> Response:
    model = _rainfall_model(model_id)
    document_id = f"{EARTH_WEATHER_RAINFALL_DATASET}:{model.model_id}"
    document = await read_latest_document(database, document_id)
    payload, stored = read_binary_payload(
        document,
        document_id,
        expected_content_type="image/png",
        signature=PNG_SIGNATURE,
    )
    return _image_response(request, payload, stored, immutable=False)


ArchiveFrom = Annotated[datetime, Query(alias="from")]
ArchiveTo = Annotated[datetime, Query(alias="to")]


@router.get(
    "/history/rainfall/stations",
    response_model=ListResponse[ArchivedObservation],
)
async def get_station_rainfall_history(
    response: Response,
    database: ReadDatabase,
    from_time: ArchiveFrom,
    to_time: ArchiveTo,
) -> ListResponse[ArchivedObservation]:
    raw_documents = await _archive_documents(
        database,
        STATION_RAINFALL_DATASET,
        "source_updated_at",
        from_time,
        to_time,
    )
    data = []
    documents = []
    for document in raw_documents:
        payload, stored = decode_json_object(
            document,
            STATION_RAINFALL_DATASET,
            validate=StationRainfallPayload.model_validate,
        )
        data.append(
            ArchivedObservation(
                source_updated_at=stored.source_updated_at,
                fetched_at=stored.fetched_at,
                observation=payload,
            )
        )
        documents.append(stored)
    _set_latest_cache(response)
    return ListResponse(
        data=data,
        meta=_list_meta(STATION_RAINFALL_DATASET, documents, len(data)),
    )


@router.get(
    "/history/rainfall/nowcast",
    response_model=ListResponse[ArchivedRainfallFrame],
)
async def get_rainfall_nowcast_history(
    response: Response,
    database: ReadDatabase,
    from_time: ArchiveFrom,
    to_time: ArchiveTo,
) -> ListResponse[ArchivedRainfallFrame]:
    raw_documents = await _archive_documents(
        database,
        GRIDDED_RAINFALL_NOWCAST_DATASET,
        "source_updated_at",
        from_time,
        to_time,
        projection={
            "_id": 0,
            "source_updated_at": 1,
            "fetched_at": 1,
            "archive_valid_times": 1,
        },
    )
    frames_by_time = {}
    documents = []
    for document in raw_documents:
        stored = validate_stored_metadata(
            document,
            GRIDDED_RAINFALL_NOWCAST_DATASET,
        )
        if stored.source_updated_at is None:
            raise StoredDataError(GRIDDED_RAINFALL_NOWCAST_DATASET)
        issue_time = stored.source_updated_at.astimezone(HONG_KONG)
        raw_valid_times = document.get("archive_valid_times")
        if raw_valid_times is None:
            valid_times = [
                issue_time + timedelta(minutes=30),
                issue_time + timedelta(minutes=60),
            ]
        elif (
            isinstance(raw_valid_times, list)
            and len(raw_valid_times) == 2
            and all(isinstance(value, datetime) for value in raw_valid_times)
        ):
            valid_times = [value.astimezone(HONG_KONG) for value in raw_valid_times]
        else:
            raise StoredDataError(GRIDDED_RAINFALL_NOWCAST_DATASET)
        documents.append(stored)
        for valid_time in valid_times:
            key = (issue_time.astimezone(UTC), valid_time.astimezone(UTC))
            frames_by_time[key] = ArchivedRainfallFrame(
                issue_time=issue_time,
                valid_time=valid_time,
                url=(
                    "/api/weather/history/rainfall/nowcast/"
                    f"{_compact_hong_kong(issue_time)}/"
                    f"{_compact_hong_kong(valid_time)}"
                ),
            )
    data = [frames_by_time[key] for key in sorted(frames_by_time)]
    _set_latest_cache(response)
    return ListResponse(
        data=data,
        meta=_list_meta(GRIDDED_RAINFALL_NOWCAST_DATASET, documents, len(data)),
    )


@router.get(
    "/history/rainfall/nowcast/{issue_time}/{valid_time}",
    response_model=DataResponse[RainfallGrid],
)
async def get_archived_rainfall_nowcast_grid(
    issue_time: str,
    valid_time: str,
    response: Response,
    database: ReadDatabase,
) -> DataResponse[RainfallGrid]:
    issue = _parse_public_time(issue_time, HONG_KONG)
    valid = _parse_public_time(valid_time, HONG_KONG)
    document = await database["archive"].find_one(
        {
            "dataset": GRIDDED_RAINFALL_NOWCAST_DATASET,
            "source_updated_at": issue.astimezone(UTC),
        },
        LATEST_PROJECTION,
    )
    if document is None:
        raise DatasetNotFoundError(GRIDDED_RAINFALL_NOWCAST_DATASET)
    grids, stored = _parse_rainfall_grids(document)
    grid = next(
        (
            item
            for item in grids
            if item.valid_at.astimezone(UTC) == valid.astimezone(UTC)
        ),
        None,
    )
    if grid is None:
        raise DatasetNotFoundError(GRIDDED_RAINFALL_NOWCAST_DATASET)
    response.headers["Cache-Control"] = IMMUTABLE_CACHE
    response.headers["ETag"] = _etag(stored.payload, stored)
    return DataResponse(
        data=grid,
        meta=_meta(GRIDDED_RAINFALL_NOWCAST_DATASET, stored),
    )


@router.get(
    "/history/radar",
    response_model=ListResponse[ArchivedRadarFrame],
)
async def get_radar_history(
    response: Response,
    database: ReadDatabase,
    from_time: ArchiveFrom,
    to_time: ArchiveTo,
) -> ListResponse[ArchivedRadarFrame]:
    raw_documents = await _archive_documents(
        database,
        RADAR_128_DATASET,
        "observed_at",
        from_time,
        to_time,
    )
    data = []
    documents = []
    for document in raw_documents:
        stored = validate_stored_document(document, RADAR_128_DATASET)
        observed_at = _document_datetime(document, "observed_at", RADAR_128_DATASET)
        data.append(
            ArchivedRadarFrame(
                observed_at=observed_at,
                bounds=_bounds(document, RADAR_128_DATASET),
                width=_positive_int(document, "raster_width", RADAR_128_DATASET),
                height=_positive_int(document, "raster_height", RADAR_128_DATASET),
                image_url=(
                    f"/api/weather/history/radar/{_compact_utc(observed_at)}/image"
                ),
            )
        )
        documents.append(stored)
    _set_latest_cache(response)
    return ListResponse(
        data=data,
        meta=_list_meta(RADAR_128_DATASET, documents, len(data)),
    )


@router.get(
    "/history/radar/{observed_at}/image",
    response_class=Response,
    responses={
        200: {"content": {"image/png": {}}},
        304: {"description": "Not modified"},
    },
)
async def get_archived_radar_image(
    observed_at: str,
    request: Request,
    database: ReadDatabase,
) -> Response:
    observed = _parse_public_time(observed_at, UTC)
    document = await database["archive"].find_one(
        {
            "dataset": RADAR_128_DATASET,
            "observed_at": observed.astimezone(UTC),
        },
        LATEST_PROJECTION,
    )
    if document is None:
        raise DatasetNotFoundError(RADAR_128_DATASET)
    payload, stored = read_binary_payload(
        document,
        RADAR_128_DATASET,
        expected_content_type="image/png",
        signature=PNG_SIGNATURE,
    )
    return _image_response(request, payload, stored, immutable=True)


@router.get(
    "/history/stations/{station_code}/forecast",
    response_model=ListResponse[ArchivedForecast],
)
async def get_station_forecast_history(
    station_code: str,
    response: Response,
    database: ReadDatabase,
    from_time: ArchiveFrom,
    to_time: ArchiveTo,
) -> ListResponse[ArchivedForecast]:
    station = _configured_station(station_code)
    raw_documents = await _archive_documents(
        database,
        OCF_STATION_FORECAST_DATASET,
        "source_updated_at",
        from_time,
        to_time,
    )
    data = []
    documents = []
    for document in raw_documents:
        payload, stored = decode_json_object(
            document,
            OCF_STATION_FORECAST_DATASET,
            validate=OcfStationForecastPayload.model_validate,
        )
        if str(payload.get("StationCode", "")).upper() != station.station_code:
            continue
        public_payload = _public_keys(payload)
        public_payload["stationLabel"] = station.label
        data.append(
            ArchivedForecast(
                source_updated_at=stored.source_updated_at,
                fetched_at=stored.fetched_at,
                forecast=public_payload,
            )
        )
        documents.append(stored)
    _set_latest_cache(response, forecast=True)
    return ListResponse(
        data=data,
        meta=_list_meta(
            f"{OCF_STATION_FORECAST_DATASET}:{station.station_code}",
            documents,
            len(data),
        ),
    )


@router.get(
    "/history/models/{model_id}/rainfall",
    response_model=ListResponse[ArchivedModelRainfall],
)
async def get_model_rainfall_history(
    model_id: str,
    response: Response,
    database: ReadDatabase,
    from_time: ArchiveFrom,
    to_time: ArchiveTo,
) -> ListResponse[ArchivedModelRainfall]:
    model = _rainfall_model(model_id)
    raw_documents = await _archive_documents(
        database,
        EARTH_WEATHER_RAINFALL_DATASET,
        "valid_at",
        from_time,
        to_time,
        extra_filter={"model": model.model_id},
    )
    data = []
    documents = []
    for document in raw_documents:
        stored = validate_stored_document(document, EARTH_WEATHER_RAINFALL_DATASET)
        valid_at = _document_datetime(
            document,
            "valid_at",
            EARTH_WEATHER_RAINFALL_DATASET,
        )
        metadata = _model_rainfall_metadata(
            document,
            model.model_id,
            image_url=(
                "/api/weather/history/models/"
                f"{model.model_id}/rainfall/{_compact_utc(valid_at)}/image"
            ),
        )
        data.append(
            ArchivedModelRainfall(
                cycle=metadata.cycle,
                valid_at=metadata.valid_at,
                lead_hours=metadata.lead_hours,
                width=metadata.width,
                height=metadata.height,
                image_url=metadata.image_url,
            )
        )
        documents.append(stored)
    _set_latest_cache(response, forecast=True)
    return ListResponse(
        data=data,
        meta=_list_meta(
            f"{EARTH_WEATHER_RAINFALL_DATASET}:{model.model_id}",
            documents,
            len(data),
        ),
    )


@router.get(
    "/history/models/{model_id}/rainfall/{valid_at}/image",
    response_class=Response,
    responses={
        200: {"content": {"image/png": {}}},
        304: {"description": "Not modified"},
    },
)
async def get_archived_model_rainfall_image(
    model_id: str,
    valid_at: str,
    request: Request,
    database: ReadDatabase,
) -> Response:
    model = _rainfall_model(model_id)
    valid = _parse_public_time(valid_at, UTC)
    document = await database["archive"].find_one(
        {
            "dataset": EARTH_WEATHER_RAINFALL_DATASET,
            "model": model.model_id,
            "valid_at": valid.astimezone(UTC),
        },
        LATEST_PROJECTION,
    )
    if document is None:
        raise DatasetNotFoundError(f"{EARTH_WEATHER_RAINFALL_DATASET}:{model.model_id}")
    payload, stored = read_binary_payload(
        document,
        EARTH_WEATHER_RAINFALL_DATASET,
        expected_content_type="image/png",
        signature=PNG_SIGNATURE,
    )
    return _image_response(request, payload, stored, immutable=True)
