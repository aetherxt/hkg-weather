import asyncio
import logging
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Annotated, Literal

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError

from .auth import require_cron_secret
from .current_weather import (
    CurrentWeatherIngestionResponse,
    CurrentWeatherNotFoundError,
    CurrentWeatherReadResponse,
    StoredCurrentWeatherError,
    ingest_current_weather,
    read_current_weather,
)
from .database import (
    close_database_clients,
    get_ingestion_database,
    get_read_database,
)
from .internal_feeds import (
    EARTH_WEATHER_MODELS,
    EARTH_WEATHER_RAINFALL_MODELS,
    EarthWeatherCycleIngestionResponse,
    EarthWeatherRainfallIngestionResponse,
    OcfStationIngestionResponse,
    TropicalCycloneIngestionResponse,
    ingest_earth_weather_cycles,
    ingest_earth_weather_rainfall,
    ingest_ocf_station_forecasts,
    ingest_radar_128,
    ingest_tropical_cyclone_tracks,
    load_ocf_stations,
)
from .json_ingestion import JsonDatasetStorageError, JsonDatasetUpstreamError
from .official_feeds import (
    GRIDDED_RAINFALL_NOWCAST_DATASET,
    LOCAL_FORECAST_DATASET,
    NINE_DAY_FORECAST_DATASET,
    STATION_RAINFALL_DATASET,
    BatchIngestionResponse,
    DatasetIngestionResponse,
    DatasetIngestionStatus,
    SmartLamppostIngestionResponse,
    ingest_gridded_rainfall,
    ingest_local_forecast,
    ingest_nine_day_forecast,
    ingest_regional_weather,
    ingest_smart_lampposts,
    ingest_station_rainfall,
    ingest_warnings,
    ingestion_status,
    load_smart_lamppost_devices,
)
from .upstream import get_http_client

logger = logging.getLogger(__name__)
DatabaseStatus = Literal["connected", "unavailable"]


class IngestionJobStatus(BaseModel):
    job: str
    ok: bool
    datasets: list[DatasetIngestionStatus]
    detail: str | None = None


class AllIngestionResponse(BaseModel):
    ok: bool
    jobs: list[IngestionJobStatus]


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await close_database_clients()


app = FastAPI(
    title="HKG Weather API",
    version="0.1.0",
    lifespan=lifespan,
)


@app.exception_handler(JsonDatasetUpstreamError)
async def json_dataset_upstream_error(
    _: Request,
    error: JsonDatasetUpstreamError,
) -> JSONResponse:
    logger.error(
        "%s upstream request failed: %s",
        error.dataset,
        type(error.__cause__).__name__,
    )
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"detail": "Upstream weather data unavailable"},
        headers={"Cache-Control": "no-store"},
    )


@app.exception_handler(JsonDatasetStorageError)
async def json_dataset_storage_error(
    _: Request,
    error: JsonDatasetStorageError,
) -> JSONResponse:
    logger.error(
        "%s database write failed: %s",
        error.dataset,
        type(error.__cause__).__name__,
    )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "Weather storage unavailable"},
        headers={"Cache-Control": "no-store"},
    )


async def check_connection(name: str, database: AsyncDatabase) -> DatabaseStatus:
    try:
        await database.command({"ping": 1})
        return "connected"
    except Exception as error:
        logger.error(
            "MongoDB %s connection failed: %s",
            name,
            type(error).__name__,
        )
        return "unavailable"


@app.get("/api/health")
async def application_health(response: Response) -> dict[str, bool]:
    response.headers["Cache-Control"] = "no-store"
    return {"ok": True}


@app.get("/api/health/database")
async def database_health() -> JSONResponse:
    if os.getenv("VERCEL_ENV") in {"preview", "production"}:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": "Not found"},
            headers={"Cache-Control": "no-store"},
        )

    ingestion, reader = await asyncio.gather(
        check_connection("ingestion", get_ingestion_database()),
        check_connection("reader", get_read_database()),
    )
    ok = ingestion == "connected" and reader == "connected"

    return JSONResponse(
        status_code=(status.HTTP_200_OK if ok else status.HTTP_503_SERVICE_UNAVAILABLE),
        content={
            "ok": ok,
            "ingestion": ingestion,
            "reader": reader,
        },
        headers={"Cache-Control": "no-store"},
    )


@app.post(
    "/api/cron/current-weather",
    response_model=CurrentWeatherIngestionResponse,
)
async def cron_current_weather(
    response: Response,
    _authorization: Annotated[None, Depends(require_cron_secret)],
    database: Annotated[AsyncDatabase, Depends(get_ingestion_database)],
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
) -> CurrentWeatherIngestionResponse:
    response.headers["Cache-Control"] = "no-store"
    result = await ingest_current_weather(database, client)

    return CurrentWeatherIngestionResponse(
        changed=result.changed,
        source_updated_at=result.source_updated_at,
        fetched_at=result.fetched_at,
    )


@app.post(
    "/api/cron/local-forecast",
    response_model=DatasetIngestionResponse,
)
async def cron_local_forecast(
    response: Response,
    _authorization: Annotated[None, Depends(require_cron_secret)],
    database: Annotated[AsyncDatabase, Depends(get_ingestion_database)],
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
) -> DatasetIngestionResponse:
    response.headers["Cache-Control"] = "no-store"
    result = await ingest_local_forecast(database, client)
    status_result = ingestion_status(LOCAL_FORECAST_DATASET, result)
    return DatasetIngestionResponse(**status_result.model_dump())


@app.post(
    "/api/cron/nine-day-forecast",
    response_model=DatasetIngestionResponse,
)
async def cron_nine_day_forecast(
    response: Response,
    _authorization: Annotated[None, Depends(require_cron_secret)],
    database: Annotated[AsyncDatabase, Depends(get_ingestion_database)],
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
) -> DatasetIngestionResponse:
    response.headers["Cache-Control"] = "no-store"
    result = await ingest_nine_day_forecast(database, client)
    status_result = ingestion_status(NINE_DAY_FORECAST_DATASET, result)
    return DatasetIngestionResponse(**status_result.model_dump())


@app.post(
    "/api/cron/warnings",
    response_model=BatchIngestionResponse,
)
async def cron_warnings(
    response: Response,
    _authorization: Annotated[None, Depends(require_cron_secret)],
    database: Annotated[AsyncDatabase, Depends(get_ingestion_database)],
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
) -> BatchIngestionResponse:
    response.headers["Cache-Control"] = "no-store"
    return BatchIngestionResponse(
        datasets=await ingest_warnings(database, client),
    )


@app.post(
    "/api/cron/station-rainfall",
    response_model=DatasetIngestionResponse,
)
async def cron_station_rainfall(
    response: Response,
    _authorization: Annotated[None, Depends(require_cron_secret)],
    database: Annotated[AsyncDatabase, Depends(get_ingestion_database)],
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
) -> DatasetIngestionResponse:
    response.headers["Cache-Control"] = "no-store"
    result = await ingest_station_rainfall(database, client)
    status_result = ingestion_status(STATION_RAINFALL_DATASET, result)
    return DatasetIngestionResponse(**status_result.model_dump())


@app.post(
    "/api/cron/rainfall-nowcast",
    response_model=DatasetIngestionResponse,
)
async def cron_rainfall_nowcast(
    response: Response,
    _authorization: Annotated[None, Depends(require_cron_secret)],
    database: Annotated[AsyncDatabase, Depends(get_ingestion_database)],
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
) -> DatasetIngestionResponse:
    response.headers["Cache-Control"] = "no-store"
    result = await ingest_gridded_rainfall(database, client)
    status_result = ingestion_status(GRIDDED_RAINFALL_NOWCAST_DATASET, result)
    return DatasetIngestionResponse(**status_result.model_dump())


@app.post(
    "/api/cron/regional-weather",
    response_model=BatchIngestionResponse,
)
async def cron_regional_weather(
    response: Response,
    _authorization: Annotated[None, Depends(require_cron_secret)],
    database: Annotated[AsyncDatabase, Depends(get_ingestion_database)],
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
) -> BatchIngestionResponse:
    response.headers["Cache-Control"] = "no-store"
    return BatchIngestionResponse(
        datasets=await ingest_regional_weather(database, client),
    )


@app.post(
    "/api/cron/smart-lampposts",
    response_model=SmartLamppostIngestionResponse,
)
async def cron_smart_lampposts(
    response: Response,
    _authorization: Annotated[None, Depends(require_cron_secret)],
    database: Annotated[AsyncDatabase, Depends(get_ingestion_database)],
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
) -> SmartLamppostIngestionResponse:
    response.headers["Cache-Control"] = "no-store"
    devices = load_smart_lamppost_devices()
    results = await ingest_smart_lampposts(database, client, devices)
    return SmartLamppostIngestionResponse(
        datasets=results,
        configured_devices=len(devices),
    )


@app.post(
    "/api/cron/ocf-station-forecasts",
    response_model=OcfStationIngestionResponse,
)
async def cron_ocf_station_forecasts(
    response: Response,
    _authorization: Annotated[None, Depends(require_cron_secret)],
    database: Annotated[AsyncDatabase, Depends(get_ingestion_database)],
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
) -> OcfStationIngestionResponse:
    response.headers["Cache-Control"] = "no-store"
    stations = load_ocf_stations()
    results = await ingest_ocf_station_forecasts(database, client, stations)
    return OcfStationIngestionResponse(
        datasets=results,
        configured_stations=len(stations),
    )


@app.post(
    "/api/cron/earth-weather-cycles",
    response_model=EarthWeatherCycleIngestionResponse,
)
async def cron_earth_weather_cycles(
    response: Response,
    _authorization: Annotated[None, Depends(require_cron_secret)],
    database: Annotated[AsyncDatabase, Depends(get_ingestion_database)],
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
) -> EarthWeatherCycleIngestionResponse:
    response.headers["Cache-Control"] = "no-store"
    results = await ingest_earth_weather_cycles(database, client)
    return EarthWeatherCycleIngestionResponse(
        datasets=results,
        configured_models=len(EARTH_WEATHER_MODELS),
    )


@app.post(
    "/api/cron/earth-weather-rainfall",
    response_model=EarthWeatherRainfallIngestionResponse,
)
async def cron_earth_weather_rainfall(
    response: Response,
    _authorization: Annotated[None, Depends(require_cron_secret)],
    database: Annotated[AsyncDatabase, Depends(get_ingestion_database)],
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
) -> EarthWeatherRainfallIngestionResponse:
    response.headers["Cache-Control"] = "no-store"
    results = await ingest_earth_weather_rainfall(database, client)
    return EarthWeatherRainfallIngestionResponse(
        datasets=results,
        configured_models=len(EARTH_WEATHER_RAINFALL_MODELS),
    )


@app.post(
    "/api/cron/radar-128",
    response_model=DatasetIngestionResponse,
)
async def cron_radar_128(
    response: Response,
    _authorization: Annotated[None, Depends(require_cron_secret)],
    database: Annotated[AsyncDatabase, Depends(get_ingestion_database)],
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
) -> DatasetIngestionResponse:
    response.headers["Cache-Control"] = "no-store"
    result = await ingest_radar_128(database, client)
    return DatasetIngestionResponse(**result.model_dump())


@app.post(
    "/api/cron/tropical-cyclones",
    response_model=TropicalCycloneIngestionResponse,
)
async def cron_tropical_cyclones(
    response: Response,
    _authorization: Annotated[None, Depends(require_cron_secret)],
    database: Annotated[AsyncDatabase, Depends(get_ingestion_database)],
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
) -> TropicalCycloneIngestionResponse:
    response.headers["Cache-Control"] = "no-store"
    results = await ingest_tropical_cyclone_tracks(database, client)
    return TropicalCycloneIngestionResponse(
        datasets=results,
        active_cyclones=len(results),
    )


@app.post(
    "/api/cron/ingest-all",
    response_model=AllIngestionResponse,
)
async def cron_ingest_all(
    response: Response,
    _authorization: Annotated[None, Depends(require_cron_secret)],
    database: Annotated[AsyncDatabase, Depends(get_ingestion_database)],
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
) -> AllIngestionResponse:
    response.headers["Cache-Control"] = "no-store"

    async def current_weather_job() -> list[DatasetIngestionStatus]:
        result = await ingest_current_weather(database, client)
        return [ingestion_status("current_weather", result)]

    async def local_forecast_job() -> list[DatasetIngestionStatus]:
        result = await ingest_local_forecast(database, client)
        return [ingestion_status(LOCAL_FORECAST_DATASET, result)]

    async def nine_day_forecast_job() -> list[DatasetIngestionStatus]:
        result = await ingest_nine_day_forecast(database, client)
        return [ingestion_status(NINE_DAY_FORECAST_DATASET, result)]

    async def station_rainfall_job() -> list[DatasetIngestionStatus]:
        result = await ingest_station_rainfall(database, client)
        return [ingestion_status(STATION_RAINFALL_DATASET, result)]

    async def gridded_rainfall_job() -> list[DatasetIngestionStatus]:
        result = await ingest_gridded_rainfall(database, client)
        return [ingestion_status(GRIDDED_RAINFALL_NOWCAST_DATASET, result)]

    async def smart_lamppost_job() -> list[DatasetIngestionStatus]:
        return await ingest_smart_lampposts(
            database,
            client,
            load_smart_lamppost_devices(),
        )

    async def ocf_station_job() -> list[DatasetIngestionStatus]:
        return await ingest_ocf_station_forecasts(
            database,
            client,
            load_ocf_stations(),
        )

    async def radar_job() -> list[DatasetIngestionStatus]:
        return [await ingest_radar_128(database, client)]

    jobs = (
        ("current_weather", current_weather_job),
        ("local_forecast", local_forecast_job),
        ("nine_day_forecast", nine_day_forecast_job),
        ("warnings", lambda: ingest_warnings(database, client)),
        ("station_rainfall", station_rainfall_job),
        ("gridded_rainfall_nowcast", gridded_rainfall_job),
        ("regional_weather", lambda: ingest_regional_weather(database, client)),
        ("smart_lampposts", smart_lamppost_job),
        ("ocf_station_forecasts", ocf_station_job),
        (
            "earth_weather_cycles",
            lambda: ingest_earth_weather_cycles(database, client),
        ),
        (
            "earth_weather_rainfall",
            lambda: ingest_earth_weather_rainfall(database, client),
        ),
        ("radar_128", radar_job),
        (
            "tropical_cyclones",
            lambda: ingest_tropical_cyclone_tracks(database, client),
        ),
    )

    semaphore = asyncio.Semaphore(3)

    async def run_named_job(
        job_name: str,
        run_job: Callable[[], Awaitable[list[DatasetIngestionStatus]]],
    ) -> IngestionJobStatus:
        async with semaphore:
            try:
                datasets = await run_job()
                return IngestionJobStatus(
                    job=job_name,
                    ok=True,
                    datasets=datasets,
                )
            except JsonDatasetUpstreamError:
                return IngestionJobStatus(
                    job=job_name,
                    ok=False,
                    datasets=[],
                    detail="upstream weather data unavailable",
                )
            except JsonDatasetStorageError:
                return IngestionJobStatus(
                    job=job_name,
                    ok=False,
                    datasets=[],
                    detail="weather storage unavailable",
                )
            except Exception:
                logger.exception("Unexpected %s batch-ingestion failure", job_name)
                return IngestionJobStatus(
                    job=job_name,
                    ok=False,
                    datasets=[],
                    detail="unexpected ingestion failure",
                )

    job_results = list(
        await asyncio.gather(
            *(run_named_job(job_name, run_job) for job_name, run_job in jobs)
        )
    )

    all_ok = all(result.ok for result in job_results)
    if not all_ok:
        response.status_code = status.HTTP_502_BAD_GATEWAY
    return AllIngestionResponse(ok=all_ok, jobs=job_results)


@app.get(
    "/api/weather/current",
    response_model=CurrentWeatherReadResponse,
)
async def get_current_weather(
    response: Response,
    database: Annotated[AsyncDatabase, Depends(get_read_database)],
) -> CurrentWeatherReadResponse:
    try:
        current_weather = await read_current_weather(database)
    except CurrentWeatherNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Current weather not found",
            headers={"Cache-Control": "no-store"},
        ) from error
    except StoredCurrentWeatherError as error:
        logger.error("Stored current-weather data is invalid")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Weather data unavailable",
            headers={"Cache-Control": "no-store"},
        ) from error
    except PyMongoError as error:
        logger.error(
            "Current-weather database read failed: %s",
            type(error).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Weather storage unavailable",
            headers={"Cache-Control": "no-store"},
        ) from error

    response.headers["Cache-Control"] = "public, max-age=0, must-revalidate"
    response.headers["Vercel-CDN-Cache-Control"] = (
        "max-age=300, stale-while-revalidate=600"
    )
    return current_weather
