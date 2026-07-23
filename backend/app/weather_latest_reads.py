import asyncio
import logging
from collections.abc import Awaitable
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Response, status
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError

from .internal_feeds import (
    EARTH_WEATHER_CYCLE_DATASET,
    EARTH_WEATHER_MODELS,
    OCF_STATION_FORECAST_DATASET,
    TROPICAL_CYCLONE_TRACK_AREA_DATASET,
    TROPICAL_CYCLONE_TRACK_DATASET,
    EarthWeatherCyclePayload,
    OcfStationForecastPayload,
    load_ocf_stations,
)
from .official_feeds import (
    ASTRONOMICAL_CSV_HEADER,
    CURRENT_WEATHER_DATASET,
    LOCAL_FORECAST_DATASET,
    MOONRISE_MOONSET_DATASET,
    NINE_DAY_FORECAST_DATASET,
    REGIONAL_TEMPERATURE_DATASET,
    REGIONAL_WIND_DATASET,
    SMART_LAMPPOST_DATASET,
    SPECIAL_WEATHER_TIPS_DATASET,
    STATION_RAINFALL_DATASET,
    SUNRISE_SUNSET_DATASET,
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
from .tropical_cyclones import (
    tropical_cyclone_geo_json,
    tropical_cyclone_track_area_geo_json,
)
from .weather_read_common import (
    HONG_KONG,
    ReadDatabase,
    configured_station,
    list_response_meta,
    number_or_none,
    public_keys,
    reader_error,
    response_meta,
    set_dashboard_cache,
    set_latest_cache,
)
from .weather_read_models import (
    AstronomicalTimes,
    DashboardSnapshot,
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
logger = logging.getLogger(__name__)


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


_WARNING_CODE_PRIORITY: dict[str, int] = {
    "WTMW": 0,
    "WTCSGNL": 1,
    "WRAIN": 2,
    "WTCPRE8": 3,
    "WL": 4,
    "WTS": 5,
    "WFIRE": 6,
    "WHOT": 7,
    "WCOLD": 8,
    "WFROST": 9,
    "WMSGNL": 10,
    "WFNTSA": 11,
}

_WARNING_TYPE_PRIORITY: dict[str, dict[str, int]] = {
    "WTCSGNL": {
        "10": 0,
        "9": 1,
        "8NE": 2,
        "8NW": 3,
        "8SE": 4,
        "8SW": 5,
        "3": 6,
        "1": 7,
    },
    "WRAIN": {
        "Black": 0,
        "Red": 1,
        "Amber": 2,
        "Yellow": 2,
    },
    "WFIRE": {
        "Red": 0,
        "Yellow": 1,
    },
}


def _warning_sort_key(item: tuple[str, Any]) -> tuple[int, int]:
    code = item[0]
    warning = item[1] if isinstance(item[1], dict) else {}
    code_priority = _WARNING_CODE_PRIORITY.get(code, 99)
    type_priority = _WARNING_TYPE_PRIORITY.get(code, {}).get(
        str(warning.get("type", "")), 0
    )
    return (code_priority, type_priority)


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

    summary = dict(sorted(payloads[0].items(), key=_warning_sort_key))

    set_latest_cache(response)
    metadata = list_response_meta("warnings", documents, len(documents))
    return DataResponse(
        data=WarningsData(
            summary=summary,
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


@router.get("/sun", response_model=DataResponse[AstronomicalTimes])
async def get_sun(
    response: Response,
    database: ReadDatabase,
) -> DataResponse[AstronomicalTimes]:
    today = datetime.now(HONG_KONG).strftime("%Y-%m-%d")

    sun_document = await read_latest_document(database, SUNRISE_SUNSET_DATASET)
    sun_rows, sun_stored = decode_csv_rows(
        sun_document,
        SUNRISE_SUNSET_DATASET,
        expected_columns=4,
        expected_header=ASTRONOMICAL_CSV_HEADER,
    )
    moon_document = await read_latest_document(database, MOONRISE_MOONSET_DATASET)
    moon_rows, moon_stored = decode_csv_rows(
        moon_document,
        MOONRISE_MOONSET_DATASET,
        expected_columns=4,
        expected_header=ASTRONOMICAL_CSV_HEADER,
    )

    try:
        sun_row = next(row for row in sun_rows if row[0].strip() == today)
        moon_row = next(
            (row for row in moon_rows if row[0].strip() == today),
            None,
        )
    except StopIteration:
        raise reader_error(
            status.HTTP_404_NOT_FOUND,
            "Today's astronomical data not found",
        ) from None

    set_latest_cache(response)
    return DataResponse(
        data=AstronomicalTimes(
            date=today,
            sunrise=sun_row[1].strip(),
            sun_transit=sun_row[2].strip(),
            sunset=sun_row[3].strip(),
            moonrise=moon_row[1].strip() if moon_row and moon_row[1].strip() else None,
            moon_transit=(
                moon_row[2].strip() if moon_row and moon_row[2].strip() else None
            ),
            moonset=moon_row[3].strip() if moon_row and moon_row[3].strip() else None,
        ),
        meta=response_meta(
            SUNRISE_SUNSET_DATASET,
            sun_stored,
        ),
    )


async def _optional_dashboard_section[Section](
    result: Awaitable[Section],
) -> Section | None:
    try:
        return await result
    except (
        DatasetNotFoundError,
        StoredDataError,
        PyMongoError,
        HTTPException,
    ) as error:
        logger.warning(
            "Dashboard section unavailable: %s",
            type(error).__name__,
        )
        return None


@router.get(
    "/dashboard",
    response_model=DataResponse[DashboardSnapshot],
)
async def get_dashboard(
    response: Response,
    database: ReadDatabase,
) -> DataResponse[DashboardSnapshot]:
    section_responses = [Response() for _ in range(9)]
    (
        warnings,
        current,
        local_forecast,
        nine_day_forecast,
        regional_temperature,
        regional_wind,
        lampposts,
        astronomical,
        station_rainfall,
    ) = await asyncio.gather(
        _optional_dashboard_section(get_warnings(section_responses[0], database)),
        _optional_dashboard_section(
            get_current_weather(section_responses[1], database)
        ),
        _optional_dashboard_section(get_local_forecast(section_responses[2], database)),
        _optional_dashboard_section(
            get_nine_day_forecast(section_responses[3], database)
        ),
        _optional_dashboard_section(
            get_regional_temperature(section_responses[4], database)
        ),
        _optional_dashboard_section(get_regional_wind(section_responses[5], database)),
        _optional_dashboard_section(get_lampposts(section_responses[6], database)),
        _optional_dashboard_section(get_sun(section_responses[7], database)),
        _optional_dashboard_section(
            get_station_rainfall(section_responses[8], database)
        ),
    )
    snapshot = DashboardSnapshot(
        warnings=warnings,
        current=current,
        local_forecast=local_forecast,
        nine_day_forecast=nine_day_forecast,
        regional_temperature=regional_temperature,
        regional_wind=regional_wind,
        lampposts=lampposts,
        astronomical=astronomical,
        station_rainfall=station_rainfall,
    )
    metadata = [
        section.meta
        for section in (
            warnings,
            current,
            local_forecast,
            nine_day_forecast,
            regional_temperature,
            regional_wind,
            lampposts,
            astronomical,
            station_rainfall,
        )
        if section is not None
    ]
    if not metadata:
        raise StoredDataError("dashboard")
    source_times = [
        item.source_updated_at for item in metadata if item.source_updated_at
    ]
    fetched_times = [item.fetched_at for item in metadata if item.fetched_at]
    set_dashboard_cache(response)
    return DataResponse(
        data=snapshot,
        meta=ResponseMetadata(
            dataset="dashboard",
            source_updated_at=max(source_times) if source_times else None,
            fetched_at=max(fetched_times) if fetched_times else None,
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
    track_cursor = (
        database["latest"]
        .find({"dataset": TROPICAL_CYCLONE_TRACK_DATASET}, LATEST_PROJECTION)
        .limit(20)
    )
    area_cursor = (
        database["latest"]
        .find({"dataset": TROPICAL_CYCLONE_TRACK_AREA_DATASET}, LATEST_PROJECTION)
        .limit(20)
    )
    raw_documents, raw_area_documents = await asyncio.gather(
        track_cursor.to_list(length=20),
        area_cursor.to_list(length=20),
    )
    areas: dict[str, StoredDocument] = {}
    for area_document in raw_area_documents:
        stored_area = validate_stored_document(
            area_document,
            TROPICAL_CYCLONE_TRACK_AREA_DATASET,
        )
        try:
            area_storm_id = str(area_document["storm_id"])
        except KeyError as error:
            raise StoredDataError(TROPICAL_CYCLONE_TRACK_AREA_DATASET) from error
        if not area_storm_id:
            raise StoredDataError(TROPICAL_CYCLONE_TRACK_AREA_DATASET)
        areas[area_storm_id] = stored_area

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
        area = areas.get(storm_id)
        cyclones.append(
            TropicalCyclone(
                storm_id=storm_id,
                name_en=name_en,
                name_zh=name_zh,
                fetched_at=stored.fetched_at,
                geo_json=tropical_cyclone_geo_json(stored.payload),
                potential_track_area_geo_json=(
                    tropical_cyclone_track_area_geo_json(area.payload)
                    if area is not None
                    else None
                ),
            )
        )
        documents.append(stored)
        if area is not None:
            documents.append(area)
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
