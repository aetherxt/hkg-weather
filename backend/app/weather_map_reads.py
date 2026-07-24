from datetime import UTC

from fastapi import APIRouter, Request, Response

from .internal_feeds import (
    EARTH_WEATHER_RAINFALL_DATASET,
    EARTH_WEATHER_WIND_DATASET,
    RADAR_128_DATASET,
)
from .official_feeds import GRIDDED_RAINFALL_NOWCAST_DATASET
from .storage_read import (
    DatasetNotFoundError,
    read_binary_payload,
    read_latest_document,
    validate_stored_document,
)
from .weather_read_common import (
    HONG_KONG,
    PNG_SIGNATURE,
    ReadDatabase,
    bounds,
    compact_hong_kong,
    document_datetime,
    image_response,
    model_rainfall_metadata,
    model_wind_metadata,
    parse_public_time,
    parse_rainfall_grids,
    positive_int,
    rainfall_model,
    response_meta,
    set_latest_cache,
    wind_model,
)
from .weather_read_models import (
    DataResponse,
    ListResponse,
    ListResponseMetadata,
    ModelRainfallMetadata,
    ModelWindMetadata,
    RadarMetadata,
    RainfallFrame,
    RainfallGrid,
)

router = APIRouter()


@router.get("/rainfall/nowcast", response_model=ListResponse[RainfallFrame])
async def get_rainfall_nowcast_index(
    response: Response,
    database: ReadDatabase,
) -> ListResponse[RainfallFrame]:
    document = await read_latest_document(database, GRIDDED_RAINFALL_NOWCAST_DATASET)
    grids, stored = parse_rainfall_grids(document)
    frames = [
        RainfallFrame(
            updated_at=grid.updated_at,
            valid_at=grid.valid_at,
            bounds=grid.bounds,
            width=grid.width,
            height=grid.height,
            url=f"/api/weather/rainfall/nowcast/{compact_hong_kong(grid.valid_at)}",
        )
        for grid in grids
    ]
    set_latest_cache(response)
    return ListResponse(
        data=frames,
        meta=ListResponseMetadata(
            **response_meta(GRIDDED_RAINFALL_NOWCAST_DATASET, stored).model_dump(),
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
    requested_time = parse_public_time(valid_time, HONG_KONG)
    document = await read_latest_document(database, GRIDDED_RAINFALL_NOWCAST_DATASET)
    grids, stored = parse_rainfall_grids(document)
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
    set_latest_cache(response)
    return DataResponse(
        data=grid,
        meta=response_meta(GRIDDED_RAINFALL_NOWCAST_DATASET, stored),
    )


@router.get("/radar", response_model=DataResponse[RadarMetadata])
async def get_radar_metadata(
    response: Response,
    database: ReadDatabase,
) -> DataResponse[RadarMetadata]:
    document = await read_latest_document(database, RADAR_128_DATASET)
    stored = validate_stored_document(document, RADAR_128_DATASET)
    data = RadarMetadata(
        observed_at=document_datetime(document, "observed_at", RADAR_128_DATASET),
        bounds=bounds(document, RADAR_128_DATASET),
        width=positive_int(document, "raster_width", RADAR_128_DATASET),
        height=positive_int(document, "raster_height", RADAR_128_DATASET),
        image_url="/api/weather/radar/image",
    )
    set_latest_cache(response)
    return DataResponse(data=data, meta=response_meta(RADAR_128_DATASET, stored))


@router.get(
    "/radar/image",
    response_class=Response,
    responses={
        200: {"content": {"image/png": {}}},
        304: {"description": "Not modified"},
    },
)
async def get_radar_image(request: Request, database: ReadDatabase) -> Response:
    document = await read_latest_document(database, RADAR_128_DATASET)
    payload, stored = read_binary_payload(
        document,
        RADAR_128_DATASET,
        expected_content_type="image/png",
        signature=PNG_SIGNATURE,
    )
    return image_response(request, payload, stored, immutable=False)


@router.get(
    "/models/{model_id}/rainfall",
    response_model=DataResponse[ModelRainfallMetadata],
)
async def get_model_rainfall_metadata(
    model_id: str,
    response: Response,
    database: ReadDatabase,
) -> DataResponse[ModelRainfallMetadata]:
    model = rainfall_model(model_id)
    document_id = f"{EARTH_WEATHER_RAINFALL_DATASET}:{model.model_id}"
    document = await read_latest_document(database, document_id)
    stored = validate_stored_document(document, document_id)
    data = model_rainfall_metadata(
        document,
        model.model_id,
        image_url=f"/api/weather/models/{model.model_id}/rainfall/image",
    )
    set_latest_cache(response)
    return DataResponse(data=data, meta=response_meta(document_id, stored))


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
    model = rainfall_model(model_id)
    document_id = f"{EARTH_WEATHER_RAINFALL_DATASET}:{model.model_id}"
    document = await read_latest_document(database, document_id)
    payload, stored = read_binary_payload(
        document,
        document_id,
        expected_content_type="image/png",
        signature=PNG_SIGNATURE,
    )
    return image_response(request, payload, stored, immutable=False)


@router.get(
    "/models/{model_id}/wind",
    response_model=DataResponse[ModelWindMetadata],
)
async def get_model_wind_metadata(
    model_id: str,
    response: Response,
    database: ReadDatabase,
) -> DataResponse[ModelWindMetadata]:
    model = wind_model(model_id)
    document_id = f"{EARTH_WEATHER_WIND_DATASET}:{model.model_id}"
    document = await read_latest_document(database, document_id)
    stored = validate_stored_document(document, document_id)
    data = model_wind_metadata(
        document,
        model.model_id,
        image_url=f"/api/weather/models/{model.model_id}/wind/image",
    )
    set_latest_cache(response)
    return DataResponse(data=data, meta=response_meta(document_id, stored))


@router.get(
    "/models/{model_id}/wind/image",
    response_class=Response,
    responses={
        200: {"content": {"image/png": {}}},
        304: {"description": "Not modified"},
    },
)
async def get_model_wind_image(
    model_id: str,
    request: Request,
    database: ReadDatabase,
) -> Response:
    model = wind_model(model_id)
    document_id = f"{EARTH_WEATHER_WIND_DATASET}:{model.model_id}"
    document = await read_latest_document(database, document_id)
    payload, stored = read_binary_payload(
        document,
        document_id,
        expected_content_type="image/png",
        signature=PNG_SIGNATURE,
    )
    return image_response(request, payload, stored, immutable=False)
