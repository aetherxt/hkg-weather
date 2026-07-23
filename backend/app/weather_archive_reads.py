import re
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from .internal_feeds import (
    EARTH_WEATHER_RAINFALL_DATASET,
    OCF_STATION_FORECAST_DATASET,
    RADAR_128_DATASET,
    TROPICAL_CYCLONE_TRACK_AREA_DATASET,
    TROPICAL_CYCLONE_TRACK_DATASET,
    OcfStationForecastPayload,
)
from .official_feeds import (
    GRIDDED_RAINFALL_NOWCAST_DATASET,
    STATION_RAINFALL_DATASET,
    StationRainfallPayload,
)
from .storage_read import (
    LATEST_PROJECTION,
    DatasetNotFoundError,
    StoredDataError,
    decode_json_object,
    read_binary_payload,
    validate_stored_document,
    validate_stored_metadata,
)
from .tropical_cyclones import (
    tropical_cyclone_geo_json,
    tropical_cyclone_track_area_geo_json,
)
from .weather_read_common import (
    HONG_KONG,
    IMMUTABLE_CACHE,
    PNG_SIGNATURE,
    ReadDatabase,
    archive_documents,
    bounds,
    compact_hong_kong,
    compact_utc,
    configured_station,
    document_datetime,
    etag,
    image_response,
    list_response_meta,
    model_rainfall_metadata,
    parse_public_time,
    parse_rainfall_grids,
    positive_int,
    public_keys,
    rainfall_model,
    response_meta,
    set_latest_cache,
)
from .weather_read_models import (
    ArchivedForecast,
    ArchivedModelRainfall,
    ArchivedObservation,
    ArchivedRadarFrame,
    ArchivedRainfallFrame,
    ArchivedTropicalCyclone,
    DataResponse,
    ListResponse,
    RainfallGrid,
)

router = APIRouter()
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
    raw_documents = await archive_documents(
        database,
        STATION_RAINFALL_DATASET,
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
    set_latest_cache(response)
    return ListResponse(
        data=data,
        meta=list_response_meta(STATION_RAINFALL_DATASET, documents, len(data)),
    )


@router.get(
    "/history/tropical-cyclones/{storm_id}",
    response_model=ListResponse[ArchivedTropicalCyclone],
)
async def get_tropical_cyclone_history(
    storm_id: str,
    response: Response,
    database: ReadDatabase,
    from_time: ArchiveFrom,
    to_time: ArchiveTo,
) -> ListResponse[ArchivedTropicalCyclone]:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", storm_id):
        raise DatasetNotFoundError(TROPICAL_CYCLONE_TRACK_DATASET)
    document_id = f"{TROPICAL_CYCLONE_TRACK_DATASET}:{storm_id}"
    raw_documents = await archive_documents(
        database,
        TROPICAL_CYCLONE_TRACK_DATASET,
        document_id,
        "fetched_at",
        from_time,
        to_time,
    )
    area_document_id = f"{TROPICAL_CYCLONE_TRACK_AREA_DATASET}:{storm_id}"
    raw_area_documents = await archive_documents(
        database,
        TROPICAL_CYCLONE_TRACK_AREA_DATASET,
        area_document_id,
        "fetched_at",
        from_time,
        to_time,
    )
    areas = []
    for area_document in raw_area_documents:
        stored_area = validate_stored_document(
            area_document,
            TROPICAL_CYCLONE_TRACK_AREA_DATASET,
        )
        try:
            area_storm_id = str(area_document["storm_id"])
        except KeyError as error:
            raise StoredDataError(TROPICAL_CYCLONE_TRACK_AREA_DATASET) from error
        if area_storm_id != storm_id:
            raise StoredDataError(TROPICAL_CYCLONE_TRACK_AREA_DATASET)
        areas.append(
            (
                stored_area,
                tropical_cyclone_track_area_geo_json(stored_area.payload),
            )
        )
    data = []
    documents = []
    for document in raw_documents:
        stored = validate_stored_document(
            document,
            TROPICAL_CYCLONE_TRACK_DATASET,
        )
        try:
            stored_storm_id = str(document["storm_id"])
            name_en = str(document["storm_name_en"])
            name_zh = str(document["storm_name_zh"])
        except KeyError as error:
            raise StoredDataError(TROPICAL_CYCLONE_TRACK_DATASET) from error
        if stored_storm_id != storm_id or not name_en:
            raise StoredDataError(TROPICAL_CYCLONE_TRACK_DATASET)
        closest_area = (
            min(
                areas,
                key=lambda area: abs(
                    (area[0].fetched_at - stored.fetched_at).total_seconds()
                ),
            )
            if areas
            else None
        )
        data.append(
            ArchivedTropicalCyclone(
                storm_id=stored_storm_id,
                name_en=name_en,
                name_zh=name_zh,
                fetched_at=stored.fetched_at,
                geo_json=tropical_cyclone_geo_json(stored.payload),
                potential_track_area_geo_json=(
                    closest_area[1] if closest_area is not None else None
                ),
            )
        )
        documents.append(stored)
        if closest_area is not None:
            documents.append(closest_area[0])
    set_latest_cache(response, forecast=True)
    return ListResponse(
        data=data,
        meta=list_response_meta(document_id, documents, len(data)),
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
    raw_documents = await archive_documents(
        database,
        GRIDDED_RAINFALL_NOWCAST_DATASET,
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
        stored = validate_stored_metadata(document, GRIDDED_RAINFALL_NOWCAST_DATASET)
        raw_valid_times = document.get("archive_valid_times")
        if (
            stored.source_updated_at is None
            or not isinstance(raw_valid_times, list)
            or len(raw_valid_times) != 2
            or not all(isinstance(value, datetime) for value in raw_valid_times)
        ):
            raise StoredDataError(GRIDDED_RAINFALL_NOWCAST_DATASET)
        issue_time = stored.source_updated_at.astimezone(HONG_KONG)
        valid_times = [value.astimezone(HONG_KONG) for value in raw_valid_times]
        documents.append(stored)
        for valid_time in valid_times:
            key = (issue_time.astimezone(UTC), valid_time.astimezone(UTC))
            frames_by_time[key] = ArchivedRainfallFrame(
                issue_time=issue_time,
                valid_time=valid_time,
                url=(
                    "/api/weather/history/rainfall/nowcast/"
                    f"{compact_hong_kong(issue_time)}/"
                    f"{compact_hong_kong(valid_time)}"
                ),
            )
    data = [frames_by_time[key] for key in sorted(frames_by_time)]
    set_latest_cache(response)
    return ListResponse(
        data=data,
        meta=list_response_meta(
            GRIDDED_RAINFALL_NOWCAST_DATASET,
            documents,
            len(data),
        ),
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
    issue = parse_public_time(issue_time, HONG_KONG)
    valid = parse_public_time(valid_time, HONG_KONG)
    document = await database["archive"].find_one(
        {
            "dataset": GRIDDED_RAINFALL_NOWCAST_DATASET,
            "document_id": GRIDDED_RAINFALL_NOWCAST_DATASET,
            "source_updated_at": issue.astimezone(UTC),
        },
        LATEST_PROJECTION,
    )
    if document is None:
        raise DatasetNotFoundError(GRIDDED_RAINFALL_NOWCAST_DATASET)
    grids, stored = parse_rainfall_grids(document)
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
    response.headers["ETag"] = etag(stored.payload, stored)
    return DataResponse(
        data=grid,
        meta=response_meta(GRIDDED_RAINFALL_NOWCAST_DATASET, stored),
    )


@router.get("/history/radar", response_model=ListResponse[ArchivedRadarFrame])
async def get_radar_history(
    response: Response,
    database: ReadDatabase,
    from_time: ArchiveFrom,
    to_time: ArchiveTo,
) -> ListResponse[ArchivedRadarFrame]:
    raw_documents = await archive_documents(
        database,
        RADAR_128_DATASET,
        RADAR_128_DATASET,
        "observed_at",
        from_time,
        to_time,
    )
    data = []
    documents = []
    for document in raw_documents:
        stored = validate_stored_document(document, RADAR_128_DATASET)
        observed_at = document_datetime(document, "observed_at", RADAR_128_DATASET)
        data.append(
            ArchivedRadarFrame(
                observed_at=observed_at,
                bounds=bounds(document, RADAR_128_DATASET),
                width=positive_int(document, "raster_width", RADAR_128_DATASET),
                height=positive_int(document, "raster_height", RADAR_128_DATASET),
                image_url=(
                    f"/api/weather/history/radar/{compact_utc(observed_at)}/image"
                ),
            )
        )
        documents.append(stored)
    set_latest_cache(response)
    return ListResponse(
        data=data,
        meta=list_response_meta(RADAR_128_DATASET, documents, len(data)),
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
    observed = parse_public_time(observed_at, UTC)
    document = await database["archive"].find_one(
        {
            "dataset": RADAR_128_DATASET,
            "document_id": RADAR_128_DATASET,
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
    return image_response(request, payload, stored, immutable=True)


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
    station = configured_station(station_code)
    document_id = f"{OCF_STATION_FORECAST_DATASET}:{station.station_code}"
    raw_documents = await archive_documents(
        database,
        OCF_STATION_FORECAST_DATASET,
        document_id,
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
            raise StoredDataError(document_id)
        public_payload = public_keys(payload)
        public_payload["stationLabel"] = station.label
        data.append(
            ArchivedForecast(
                source_updated_at=stored.source_updated_at,
                fetched_at=stored.fetched_at,
                forecast=public_payload,
            )
        )
        documents.append(stored)
    set_latest_cache(response, forecast=True)
    return ListResponse(
        data=data,
        meta=list_response_meta(document_id, documents, len(data)),
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
    model = rainfall_model(model_id)
    document_id = f"{EARTH_WEATHER_RAINFALL_DATASET}:{model.model_id}"
    raw_documents = await archive_documents(
        database,
        EARTH_WEATHER_RAINFALL_DATASET,
        document_id,
        "valid_at",
        from_time,
        to_time,
    )
    data = []
    documents = []
    for document in raw_documents:
        stored = validate_stored_document(document, EARTH_WEATHER_RAINFALL_DATASET)
        valid_at = document_datetime(
            document,
            "valid_at",
            EARTH_WEATHER_RAINFALL_DATASET,
        )
        metadata = model_rainfall_metadata(
            document,
            model.model_id,
            image_url=(
                "/api/weather/history/models/"
                f"{model.model_id}/rainfall/{compact_utc(valid_at)}/image"
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
    set_latest_cache(response, forecast=True)
    return ListResponse(
        data=data,
        meta=list_response_meta(document_id, documents, len(data)),
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
    model = rainfall_model(model_id)
    valid = parse_public_time(valid_at, UTC)
    document_id = f"{EARTH_WEATHER_RAINFALL_DATASET}:{model.model_id}"
    document = await database["archive"].find_one(
        {
            "dataset": EARTH_WEATHER_RAINFALL_DATASET,
            "document_id": document_id,
            "valid_at": valid.astimezone(UTC),
        },
        LATEST_PROJECTION,
    )
    if document is None:
        raise DatasetNotFoundError(document_id)
    payload, stored = read_binary_payload(
        document,
        EARTH_WEATHER_RAINFALL_DATASET,
        expected_content_type="image/png",
        signature=PNG_SIGNATURE,
    )
    return image_response(request, payload, stored, immutable=True)
