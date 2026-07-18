import hashlib
import math
import re
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, Request, Response, status
from pydantic.alias_generators import to_camel
from pymongo import ASCENDING
from pymongo.asynchronous.database import AsyncDatabase

from .database import get_read_database
from .internal_feeds import (
    EARTH_WEATHER_RAINFALL_DATASET,
    EARTH_WEATHER_RAINFALL_MODELS,
    load_ocf_stations,
)
from .official_feeds import GRIDDED_RAINFALL_NOWCAST_DATASET
from .rainfall_nowcast import parse_gridded_rainfall_csv
from .storage_read import (
    LATEST_PROJECTION,
    StoredDataError,
    StoredDocument,
    StoredMetadata,
    validate_stored_document,
)
from .weather_read_models import (
    Bounds,
    ListResponseMetadata,
    ModelRainfallMetadata,
    RainfallGrid,
    ResponseMetadata,
    StationItem,
)

HONG_KONG = ZoneInfo("Asia/Hong_Kong")
MAX_ARCHIVE_RANGE = timedelta(days=3)
MAX_ARCHIVE_RESULTS = 512
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

LATEST_BROWSER_CACHE = "public, max-age=0, must-revalidate"
FAST_CDN_CACHE = "max-age=60, stale-while-revalidate=300"
CURRENT_CDN_CACHE = "max-age=300, stale-while-revalidate=600"
FORECAST_CDN_CACHE = "max-age=600, stale-while-revalidate=1200"
IMMUTABLE_CACHE = "public, max-age=31536000, immutable"

ReadDatabase = Annotated[AsyncDatabase, Depends(get_read_database)]


def response_meta(
    dataset: str,
    stored: StoredMetadata | None,
) -> ResponseMetadata:
    return ResponseMetadata(
        dataset=dataset,
        source_updated_at=(stored.source_updated_at if stored else None),
        fetched_at=(stored.fetched_at if stored else None),
    )


def list_response_meta(
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


def set_latest_cache(
    response: Response,
    *,
    forecast: bool = False,
    current: bool = False,
) -> None:
    response.headers["Cache-Control"] = LATEST_BROWSER_CACHE
    if forecast:
        cdn_cache = FORECAST_CDN_CACHE
    elif current:
        cdn_cache = CURRENT_CDN_CACHE
    else:
        cdn_cache = FAST_CDN_CACHE
    response.headers["Vercel-CDN-Cache-Control"] = cdn_cache


def reader_error(status_code: int, detail: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=detail,
        headers={"Cache-Control": "no-store"},
    )


def public_keys(value: Any) -> Any:
    if isinstance(value, list):
        return [public_keys(item) for item in value]
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
        normalized[public_key] = public_keys(item)
    return normalized


def number_or_none(value: str, missing_values: frozenset[str]) -> float | None:
    cleaned = value.strip()
    if cleaned.upper() in missing_values:
        return None
    try:
        number = float(cleaned)
    except ValueError as error:
        raise ValueError("measurement is not numeric") from error
    if not math.isfinite(number):
        raise ValueError("measurement is not finite")
    return number


def content_hash(payload: bytes, stored: StoredDocument) -> str:
    return stored.content_hash or hashlib.sha256(payload).hexdigest()


def etag(payload: bytes, stored: StoredDocument) -> str:
    return f'"{content_hash(payload, stored)}"'


def image_response(
    request: Request,
    payload: bytes,
    stored: StoredDocument,
    *,
    immutable: bool,
) -> Response:
    response_etag = etag(payload, stored)
    headers = {
        "Cache-Control": IMMUTABLE_CACHE if immutable else LATEST_BROWSER_CACHE,
        "ETag": response_etag,
        "Content-Length": str(len(payload)),
    }
    if not immutable:
        headers["Vercel-CDN-Cache-Control"] = FAST_CDN_CACHE
    if request.headers.get("if-none-match") == response_etag:
        headers.pop("Content-Length")
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    return Response(content=payload, media_type="image/png", headers=headers)


def parse_public_time(value: str, default_timezone: tzinfo = UTC) -> datetime:
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
        raise reader_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Invalid timestamp",
        ) from error


def compact_hong_kong(value: datetime) -> str:
    return value.astimezone(HONG_KONG).strftime("%Y%m%d%H%M")


def compact_utc(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def validate_range(
    from_time: datetime,
    to_time: datetime,
) -> tuple[datetime, datetime]:
    start = from_time.replace(tzinfo=UTC) if from_time.tzinfo is None else from_time
    end = to_time.replace(tzinfo=UTC) if to_time.tzinfo is None else to_time
    start = start.astimezone(UTC)
    end = end.astimezone(UTC)
    if end < start:
        raise reader_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "to must not precede from",
        )
    if end - start > MAX_ARCHIVE_RANGE:
        raise reader_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Archive range must not exceed three days",
        )
    return start, end


async def archive_documents(
    database: AsyncDatabase,
    dataset: str,
    document_id: str,
    field: str,
    from_time: datetime,
    to_time: datetime,
    *,
    projection: dict[str, int] | None = None,
) -> list[dict[str, Any]]:
    start, end = validate_range(from_time, to_time)
    query: dict[str, Any] = {
        "dataset": dataset,
        "document_id": document_id,
        field: {"$gte": start, "$lte": end},
    }
    cursor = database["archive"].find(query, projection or LATEST_PROJECTION)
    cursor = cursor.sort(field, ASCENDING).limit(MAX_ARCHIVE_RESULTS + 1)
    documents = await cursor.to_list(length=MAX_ARCHIVE_RESULTS + 1)
    if len(documents) > MAX_ARCHIVE_RESULTS:
        raise reader_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Archive query contains too many results",
        )
    return documents


def parse_rainfall_grids(
    document: dict[str, Any],
) -> tuple[list[RainfallGrid], StoredDocument]:
    stored = validate_stored_document(document, GRIDDED_RAINFALL_NOWCAST_DATASET)
    try:
        parsed_grids = parse_gridded_rainfall_csv(stored.payload)
    except (UnicodeError, ValueError) as error:
        raise StoredDataError(GRIDDED_RAINFALL_NOWCAST_DATASET) from error
    grids = [
        RainfallGrid(
            updated_at=grid.updated_at,
            valid_at=grid.valid_at,
            bounds=Bounds(
                north=max(grid.latitudes),
                south=min(grid.latitudes),
                east=max(grid.longitudes),
                west=min(grid.longitudes),
            ),
            width=len(grid.longitudes),
            height=len(grid.latitudes),
            values=list(grid.values),
        )
        for grid in parsed_grids
    ]
    return grids, stored


def bounds(document: dict[str, Any], dataset: str) -> Bounds:
    try:
        result = Bounds.model_validate(document["bounds"])
        if result.north <= result.south or result.east <= result.west:
            raise ValueError("invalid bounds")
        return result
    except (KeyError, TypeError, ValueError) as error:
        raise StoredDataError(dataset) from error


def positive_int(document: dict[str, Any], key: str, dataset: str) -> int:
    value = document.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise StoredDataError(dataset)
    return value


def document_datetime(document: dict[str, Any], key: str, dataset: str) -> datetime:
    value = document.get(key)
    if not isinstance(value, datetime):
        raise StoredDataError(dataset)
    return value


def configured_station(station_code: str) -> StationItem:
    normalized = station_code.upper()
    station = next(
        (item for item in load_ocf_stations() if item.station_code == normalized),
        None,
    )
    if station is None:
        raise reader_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Unsupported station code",
        )
    return StationItem(station_code=station.station_code, label=station.label)


def rainfall_model(model_id: str):
    model = next(
        (item for item in EARTH_WEATHER_RAINFALL_MODELS if item.model_id == model_id),
        None,
    )
    if model is None:
        raise reader_error(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Unsupported rainfall model",
        )
    return model


def model_rainfall_metadata(
    document: dict[str, Any],
    model_id: str,
    *,
    image_url: str,
) -> ModelRainfallMetadata:
    model = rainfall_model(model_id)
    if document.get("model") != model.model_id:
        raise StoredDataError(f"{EARTH_WEATHER_RAINFALL_DATASET}:{model_id}")
    return ModelRainfallMetadata(
        model_id=model.model_id,
        label=model.label,
        cycle=document_datetime(document, "base_time", EARTH_WEATHER_RAINFALL_DATASET),
        lead_hours=positive_int(
            document,
            "lead_hours",
            EARTH_WEATHER_RAINFALL_DATASET,
        ),
        valid_at=document_datetime(
            document,
            "valid_at",
            EARTH_WEATHER_RAINFALL_DATASET,
        ),
        width=positive_int(
            document,
            "raster_width",
            EARTH_WEATHER_RAINFALL_DATASET,
        ),
        height=positive_int(
            document,
            "raster_height",
            EARTH_WEATHER_RAINFALL_DATASET,
        ),
        image_url=image_url,
    )
