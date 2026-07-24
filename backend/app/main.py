import asyncio
import logging
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from functools import partial
from typing import Annotated, Literal

import httpx
from fastapi import Depends, FastAPI, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError

from .auth import require_cron_secret
from .database import (
    close_database_clients,
    get_ingestion_database,
    get_read_database,
)
from .ingestion import (
    DatasetIngestionResult,
    DatasetStorageError,
    DatasetUpstreamError,
)
from .internal_feeds import (
    EARTH_WEATHER_MODELS,
    EARTH_WEATHER_RAINFALL_MODELS,
    EARTH_WEATHER_WIND_MODELS,
    TROPICAL_CYCLONE_TRACK_DATASET,
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
from .official_feeds import (
    CURRENT_WEATHER_DATASET,
    GRIDDED_RAINFALL_NOWCAST_DATASET,
    LOCAL_FORECAST_DATASET,
    NINE_DAY_FORECAST_DATASET,
    STATION_RAINFALL_DATASET,
    BatchIngestionResponse,
    DatasetIngestionResponse,
    DatasetIngestionStatus,
    SmartLamppostIngestionResponse,
    ingest_astronomical_times,
    ingest_current_weather,
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
from .storage_read import DatasetNotFoundError, StoredDataError
from .upstream import get_http_client
from .weather_reads import router as weather_reader_router

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


type IngestionJobRunner = Callable[
    [AsyncDatabase, httpx.AsyncClient],
    Awaitable[list[DatasetIngestionStatus]],
]


@dataclass(frozen=True)
class IngestionJobDefinition:
    name: str
    run: IngestionJobRunner


async def _single_dataset_job(
    database: AsyncDatabase,
    client: httpx.AsyncClient,
    *,
    dataset: str,
    ingest: Callable[
        [AsyncDatabase, httpx.AsyncClient],
        Awaitable[DatasetIngestionResult],
    ],
) -> list[DatasetIngestionStatus]:
    return [ingestion_status(dataset, await ingest(database, client))]


async def _radar_job(
    database: AsyncDatabase,
    client: httpx.AsyncClient,
) -> list[DatasetIngestionStatus]:
    return [await ingest_radar_128(database, client)]


async def _smart_lamppost_job(
    database: AsyncDatabase,
    client: httpx.AsyncClient,
) -> list[DatasetIngestionStatus]:
    return await ingest_smart_lampposts(
        database,
        client,
        load_smart_lamppost_devices(),
    )


async def _ocf_station_job(
    database: AsyncDatabase,
    client: httpx.AsyncClient,
) -> list[DatasetIngestionStatus]:
    return await ingest_ocf_station_forecasts(
        database,
        client,
        load_ocf_stations(),
    )


def ingestion_jobs() -> tuple[IngestionJobDefinition, ...]:
    return (
        IngestionJobDefinition(
            "current_weather",
            partial(
                _single_dataset_job,
                dataset=CURRENT_WEATHER_DATASET,
                ingest=ingest_current_weather,
            ),
        ),
        IngestionJobDefinition(
            "local_forecast",
            partial(
                _single_dataset_job,
                dataset=LOCAL_FORECAST_DATASET,
                ingest=ingest_local_forecast,
            ),
        ),
        IngestionJobDefinition(
            "nine_day_forecast",
            partial(
                _single_dataset_job,
                dataset=NINE_DAY_FORECAST_DATASET,
                ingest=ingest_nine_day_forecast,
            ),
        ),
        IngestionJobDefinition("warnings", ingest_warnings),
        IngestionJobDefinition(
            "station_rainfall",
            partial(
                _single_dataset_job,
                dataset=STATION_RAINFALL_DATASET,
                ingest=ingest_station_rainfall,
            ),
        ),
        IngestionJobDefinition(
            "gridded_rainfall_nowcast",
            partial(
                _single_dataset_job,
                dataset=GRIDDED_RAINFALL_NOWCAST_DATASET,
                ingest=ingest_gridded_rainfall,
            ),
        ),
        IngestionJobDefinition("regional_weather", ingest_regional_weather),
        IngestionJobDefinition("astronomical_times", ingest_astronomical_times),
        IngestionJobDefinition("smart_lampposts", _smart_lamppost_job),
        IngestionJobDefinition("ocf_station_forecasts", _ocf_station_job),
        IngestionJobDefinition("earth_weather_cycles", ingest_earth_weather_cycles),
        IngestionJobDefinition(
            "earth_weather_rainfall",
            ingest_earth_weather_rainfall,
        ),
        IngestionJobDefinition("radar_128", _radar_job),
        IngestionJobDefinition(
            "tropical_cyclones",
            ingest_tropical_cyclone_tracks,
        ),
    )


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await close_database_clients()


app = FastAPI(
    title="HKG Weather API",
    version="0.1.0",
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def request_validation_error(
    _: Request,
    error: RequestValidationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": jsonable_encoder(error.errors())},
        headers={"Cache-Control": "no-store"},
    )


@app.exception_handler(DatasetNotFoundError)
async def dataset_not_found_error(
    _: Request,
    error: DatasetNotFoundError,
) -> JSONResponse:
    logger.info("Stored weather dataset not found: %s", error.dataset)
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": "Weather data not found"},
        headers={"Cache-Control": "no-store"},
    )


@app.exception_handler(StoredDataError)
async def stored_data_error(
    _: Request,
    error: StoredDataError,
) -> JSONResponse:
    logger.error("Stored weather dataset is invalid: %s", error.dataset)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "Weather data unavailable"},
        headers={"Cache-Control": "no-store"},
    )


@app.exception_handler(PyMongoError)
async def weather_storage_error(
    _: Request,
    error: PyMongoError,
) -> JSONResponse:
    logger.error("Weather database read failed: %s", type(error).__name__)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "Weather storage unavailable"},
        headers={"Cache-Control": "no-store"},
    )


@app.exception_handler(DatasetUpstreamError)
async def dataset_upstream_error(
    _: Request,
    error: DatasetUpstreamError,
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


@app.exception_handler(DatasetStorageError)
async def dataset_storage_error(
    _: Request,
    error: DatasetStorageError,
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
    response_model=DatasetIngestionResponse,
)
async def cron_current_weather(
    response: Response,
    _authorization: Annotated[None, Depends(require_cron_secret)],
    database: Annotated[AsyncDatabase, Depends(get_ingestion_database)],
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
) -> DatasetIngestionResponse:
    response.headers["Cache-Control"] = "no-store"
    result = await ingest_current_weather(database, client)
    status_result = ingestion_status(CURRENT_WEATHER_DATASET, result)
    return DatasetIngestionResponse(**status_result.model_dump())


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
    "/api/cron/astronomical-times",
    response_model=BatchIngestionResponse,
)
async def cron_astronomical_times(
    response: Response,
    _authorization: Annotated[None, Depends(require_cron_secret)],
    database: Annotated[AsyncDatabase, Depends(get_ingestion_database)],
    client: Annotated[httpx.AsyncClient, Depends(get_http_client)],
) -> BatchIngestionResponse:
    response.headers["Cache-Control"] = "no-store"
    return BatchIngestionResponse(
        datasets=await ingest_astronomical_times(database, client),
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
        configured_wind_models=len(EARTH_WEATHER_WIND_MODELS),
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
        active_cyclones=sum(
            result.dataset.startswith(f"{TROPICAL_CYCLONE_TRACK_DATASET}:")
            for result in results
        ),
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

    semaphore = asyncio.Semaphore(3)

    async def run_job(
        job: IngestionJobDefinition,
    ) -> IngestionJobStatus:
        async with semaphore:
            try:
                datasets = await job.run(database, client)
                return IngestionJobStatus(
                    job=job.name,
                    ok=True,
                    datasets=datasets,
                )
            except DatasetUpstreamError:
                return IngestionJobStatus(
                    job=job.name,
                    ok=False,
                    datasets=[],
                    detail="upstream weather data unavailable",
                )
            except DatasetStorageError:
                return IngestionJobStatus(
                    job=job.name,
                    ok=False,
                    datasets=[],
                    detail="weather storage unavailable",
                )
            except Exception:
                logger.exception("Unexpected %s batch-ingestion failure", job.name)
                return IngestionJobStatus(
                    job=job.name,
                    ok=False,
                    datasets=[],
                    detail="unexpected ingestion failure",
                )

    job_results = list(
        await asyncio.gather(*(run_job(job) for job in ingestion_jobs()))
    )

    all_ok = all(result.ok for result in job_results)
    if not all_ok:
        response.status_code = status.HTTP_502_BAD_GATEWAY
    return AllIngestionResponse(ok=all_ok, jobs=job_results)


app.include_router(weather_reader_router)
