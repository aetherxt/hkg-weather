from fastapi import APIRouter

from .weather_archive_reads import router as archive_router
from .weather_latest_reads import router as latest_router
from .weather_map_reads import router as map_router
from .weather_read_models import ErrorResponse

router = APIRouter(
    prefix="/api/weather",
    tags=["weather"],
    responses={
        404: {"model": ErrorResponse, "description": "Stored data not found"},
        422: {"model": ErrorResponse, "description": "Invalid parameters"},
        503: {"model": ErrorResponse, "description": "Weather data unavailable"},
    },
)
router.include_router(latest_router)
router.include_router(map_router)
router.include_router(archive_router)
