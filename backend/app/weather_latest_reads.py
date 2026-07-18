import xml.etree.ElementTree as ElementTree
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Response, status
from pymongo.asynchronous.database import AsyncDatabase

from .internal_feeds import (
    EARTH_WEATHER_CYCLE_DATASET,
    EARTH_WEATHER_MODELS,
    OCF_STATION_FORECAST_DATASET,
    TROPICAL_CYCLONE_TRACK_DATASET,
    EarthWeatherCyclePayload,
    OcfStationForecastPayload,
    load_ocf_stations,
)
from .official_feeds import (
    CURRENT_WEATHER_DATASET,
    LOCAL_FORECAST_DATASET,
    NINE_DAY_FORECAST_DATASET,
    REGIONAL_TEMPERATURE_DATASET,
    REGIONAL_WIND_DATASET,
    SMART_LAMPPOST_DATASET,
    SPECIAL_WEATHER_TIPS_DATASET,
    STATION_RAINFALL_DATASET,
    TEMPERATURE_CSV_HEADER,
    TEMPERATURE_MISSING_VALUES,
    WARNING_INFORMATION_DATASET,
    WARNING_SUMMARY_DATASET,
    WIND_CSV_HEADER,
    WIND_GUST_MISSING_VALUES,
    WIND_SPEED_MISSING_VALUES,
    CurrentWeatherPayload,
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
    decode_csv_rows,
    decode_json_object,
    read_latest_document,
    validate_stored_document,
)
from .weather_read_common import (
    ReadDatabase,
    configured_station,
    list_response_meta,
    number_or_none,
    public_keys,
    reader_error,
    response_meta,
    set_latest_cache,
)
from .weather_read_models import (
    DataResponse,
    LamppostReading,
    ListResponse,
    ListResponseMetadata,
    ModelItem,
    ResponseMetadata,
    StationItem,
    TemperatureReading,
    TropicalCyclone,
    WarningsData,
    WindReading,
)

router = APIRouter()


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
            try:
                coordinates = [
                    [float(item) for item in token.split(",")][:3]
                    for token in coordinate_element.text.split()
                ]
                if any(len(item) < 2 for item in coordinates):
                    raise ValueError("coordinate has too few values")
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
                coordinates = [
                    [float(item) for item in token.split(",")][:3]
                    for token in element.text.split()
                ]
                if any(len(item) < 2 for item in coordinates):
                    raise ValueError("coordinate has too few values")
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


@router.get("/current", response_model=DataResponse[dict[str, Any]])
async def get_current_weather(
    response: Response,
    database: ReadDatabase,
) -> DataResponse[dict[str, Any]]:
    document = await read_latest_document(database, CURRENT_WEATHER_DATASET)
    payload, stored = decode_json_object(
        document,
        CURRENT_WEATHER_DATASET,
        validate=CurrentWeatherPayload.model_validate,
    )
    set_latest_cache(response, current=True)
    return DataResponse(
        data=payload,
        meta=response_meta(CURRENT_WEATHER_DATASET, stored),
    )


@router.get("/forecast/local", response_model=DataResponse[dict[str, Any]])
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
    set_latest_cache(response, forecast=True)
    return DataResponse(
        data=payload,
        meta=response_meta(LOCAL_FORECAST_DATASET, stored),
    )


@router.get("/forecast/nine-day", response_model=DataResponse[dict[str, Any]])
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
    set_latest_cache(response, forecast=True)
    return DataResponse(
        data=payload,
        meta=response_meta(NINE_DAY_FORECAST_DATASET, stored),
    )


@router.get("/warnings", response_model=DataResponse[WarningsData])
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
        payload, stored = decode_json_object(document, dataset, validate=validator)
        payloads.append(payload)
        documents.append(stored)

    set_latest_cache(response)
    metadata = list_response_meta("warnings", documents, len(documents))
    return DataResponse(
        data=WarningsData(
            summary=payloads[0],
            information=payloads[1],
            special_weather_tips=payloads[2],
        ),
        meta=ResponseMetadata(
            dataset="warnings",
            source_updated_at=metadata.source_updated_at,
            fetched_at=metadata.fetched_at,
        ),
    )


@router.get("/rainfall/stations", response_model=DataResponse[dict[str, Any]])
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
    set_latest_cache(response)
    return DataResponse(
        data=payload,
        meta=response_meta(STATION_RAINFALL_DATASET, stored),
    )


@router.get("/regional/temperature", response_model=ListResponse[TemperatureReading])
async def get_regional_temperature(
    response: Response,
    database: ReadDatabase,
) -> ListResponse[TemperatureReading]:
    document = await read_latest_document(database, REGIONAL_TEMPERATURE_DATASET)
    rows, stored = decode_csv_rows(
        document,
        REGIONAL_TEMPERATURE_DATASET,
        expected_columns=3,
        expected_header=TEMPERATURE_CSV_HEADER,
    )
    try:
        readings = [
            TemperatureReading(
                observed_at=parse_hong_kong_time(row[0]),
                station=row[1].strip(),
                temperature_c=number_or_none(row[2], TEMPERATURE_MISSING_VALUES),
            )
            for row in rows
        ]
        if any(not item.station for item in readings):
            raise ValueError("station is empty")
    except ValueError as error:
        raise StoredDataError(REGIONAL_TEMPERATURE_DATASET) from error
    set_latest_cache(response)
    return ListResponse(
        data=readings,
        meta=ListResponseMetadata(
            **response_meta(REGIONAL_TEMPERATURE_DATASET, stored).model_dump(),
            count=len(readings),
        ),
    )


@router.get("/regional/wind", response_model=ListResponse[WindReading])
async def get_regional_wind(
    response: Response,
    database: ReadDatabase,
) -> ListResponse[WindReading]:
    document = await read_latest_document(database, REGIONAL_WIND_DATASET)
    rows, stored = decode_csv_rows(
        document,
        REGIONAL_WIND_DATASET,
        expected_columns=5,
        expected_header=WIND_CSV_HEADER,
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
                mean_wind_speed_kmh=number_or_none(
                    row[3],
                    WIND_SPEED_MISSING_VALUES,
                ),
                maximum_gust_kmh=number_or_none(
                    row[4],
                    WIND_GUST_MISSING_VALUES,
                ),
            )
            for row in rows
        ]
        if any(not item.station for item in readings):
            raise ValueError("station is empty")
    except ValueError as error:
        raise StoredDataError(REGIONAL_WIND_DATASET) from error
    set_latest_cache(response)
    return ListResponse(
        data=readings,
        meta=ListResponseMetadata(
            **response_meta(REGIONAL_WIND_DATASET, stored).model_dump(),
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
        raise reader_error(
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
            reading=public_keys(payload),
        ),
        stored,
    )


@router.get("/lampposts", response_model=ListResponse[LamppostReading])
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
    set_latest_cache(response)
    return ListResponse(
        data=readings,
        meta=list_response_meta(SMART_LAMPPOST_DATASET, documents, len(readings)),
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
    set_latest_cache(response)
    return DataResponse(
        data=reading,
        meta=response_meta(
            f"{SMART_LAMPPOST_DATASET}:{lamppost_id}:{device_id}",
            stored,
        ),
    )


@router.get("/stations", response_model=ListResponse[StationItem])
async def get_stations(response: Response) -> ListResponse[StationItem]:
    stations = [
        StationItem(station_code=item.station_code, label=item.label)
        for item in load_ocf_stations()
    ]
    set_latest_cache(response, forecast=True)
    return ListResponse(
        data=stations,
        meta=ListResponseMetadata(
            dataset="ocf_stations",
            source_updated_at=None,
            fetched_at=None,
            count=len(stations),
        ),
    )


@router.get(
    "/stations/{station_code}/forecast",
    response_model=DataResponse[dict[str, Any]],
)
async def get_station_forecast(
    station_code: str,
    response: Response,
    database: ReadDatabase,
) -> DataResponse[dict[str, Any]]:
    station = configured_station(station_code)
    document_id = f"{OCF_STATION_FORECAST_DATASET}:{station.station_code}"
    document = await read_latest_document(database, document_id)
    payload, stored = decode_json_object(
        document,
        document_id,
        validate=OcfStationForecastPayload.model_validate,
    )
    public_payload = public_keys(payload)
    public_payload["stationLabel"] = station.label
    set_latest_cache(response, forecast=True)
    return DataResponse(data=public_payload, meta=response_meta(document_id, stored))


@router.get("/models", response_model=ListResponse[ModelItem])
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
    set_latest_cache(response)
    return ListResponse(
        data=models,
        meta=list_response_meta(EARTH_WEATHER_CYCLE_DATASET, documents, len(models)),
    )


@router.get("/tropical-cyclones", response_model=ListResponse[TropicalCyclone])
async def get_tropical_cyclones(
    response: Response,
    database: ReadDatabase,
) -> ListResponse[TropicalCyclone]:
    cursor = (
        database["latest"]
        .find({"dataset": TROPICAL_CYCLONE_TRACK_DATASET}, LATEST_PROJECTION)
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
    set_latest_cache(response)
    return ListResponse(
        data=cyclones,
        meta=list_response_meta(
            TROPICAL_CYCLONE_TRACK_DATASET,
            documents,
            len(cyclones),
        ),
    )
