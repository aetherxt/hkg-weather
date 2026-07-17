import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Literal

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
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
from .json_ingestion import JsonDatasetStorageError, JsonDatasetUpstreamError
from .upstream import get_http_client

logger = logging.getLogger(__name__)
DatabaseStatus = Literal["connected", "unavailable"]


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
