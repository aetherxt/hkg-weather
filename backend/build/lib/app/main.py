import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Response, status
from fastapi.responses import JSONResponse
from pymongo.asynchronous.database import AsyncDatabase

from .database import (
    close_database_clients,
    get_ingestion_database,
    get_read_database,
)

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
