import asyncio
import csv
import io
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from .ingestion import DatasetUpstreamError, ValidatedPayload, fetch_with_retry

HONG_KONG = ZoneInfo("Asia/Hong_Kong")
FORECAST_INTERVAL = timedelta(minutes=30)
NOWCAST_RANGE_COUNT = 4
NOWCAST_DOWNLOAD_TIMEOUT_SECONDS = 50.0
CONTENT_RANGE_PATTERN = re.compile(r"bytes (\d+)-(\d+)/(\d+)")
GRIDDED_RAINFALL_HEADER = (
    "Updated Date and Time (in Hong Kong Time)",
    "Ending Date and Time (in Hong Kong Time)",
    "Latitude (degree)",
    "Longitude (degree)",
    "Half-hourly Nowcast Accumulated Rainfall (mm)",
)


@dataclass(frozen=True)
class RainfallGridData:
    updated_at: datetime
    valid_at: datetime
    latitudes: tuple[float, ...]
    longitudes: tuple[float, ...]
    values: tuple[float, ...]
    source_rows: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class GriddedRainfallDownload:
    payload: bytes
    etag: str
    content_type: str


def _response_etag(response: httpx.Response) -> str:
    etag = response.headers.get("etag", "").strip()
    if not etag:
        raise ValueError("gridded rainfall response omitted its ETag")
    return etag


def _content_range(response: httpx.Response) -> tuple[int, int, int]:
    match = CONTENT_RANGE_PATTERN.fullmatch(
        response.headers.get("content-range", "").strip()
    )
    if match is None:
        raise ValueError("gridded rainfall response has an invalid Content-Range")
    return tuple(int(value) for value in match.groups())


def _byte_ranges(total_size: int) -> tuple[tuple[int, int], ...]:
    if total_size < NOWCAST_RANGE_COUNT:
        raise ValueError("gridded rainfall response is unexpectedly small")
    chunk_size = math.ceil(total_size / NOWCAST_RANGE_COUNT)
    return tuple(
        (start, min(start + chunk_size - 1, total_size - 1))
        for start in range(0, total_size, chunk_size)
    )


async def fetch_gridded_rainfall_csv(
    client: httpx.AsyncClient,
    url: str,
    dataset: str,
    *,
    known_etag: str | None,
    timeout_seconds: float = NOWCAST_DOWNLOAD_TIMEOUT_SECONDS,
) -> GriddedRainfallDownload | None:
    probe_headers = {"Range": "bytes=0-0"}
    if known_etag:
        probe_headers["If-None-Match"] = known_etag

    try:
        async with asyncio.timeout(timeout_seconds):
            probe = await fetch_with_retry(
                client,
                url,
                dataset,
                headers=probe_headers,
                accepted_statuses=frozenset({httpx.codes.NOT_MODIFIED}),
            )
            if probe.status_code == httpx.codes.NOT_MODIFIED:
                return None
            if probe.status_code != httpx.codes.PARTIAL_CONTENT:
                raise ValueError(
                    "gridded rainfall source does not support byte ranges"
                )

            etag = _response_etag(probe)
            probe_start, probe_end, total_size = _content_range(probe)
            if (probe_start, probe_end) != (0, 0) or len(probe.content) != 1:
                raise ValueError("gridded rainfall range probe is invalid")

            ranges = _byte_ranges(total_size)

            async def fetch_range(start: int, end: int) -> bytes:
                response = await fetch_with_retry(
                    client,
                    url,
                    dataset,
                    headers={
                        "Range": f"bytes={start}-{end}",
                        "If-Match": etag,
                    },
                )
                if response.status_code != httpx.codes.PARTIAL_CONTENT:
                    raise ValueError("gridded rainfall byte range was not honoured")
                if _response_etag(response) != etag:
                    raise ValueError("gridded rainfall changed during download")
                if _content_range(response) != (start, end, total_size):
                    raise ValueError("gridded rainfall byte range is inconsistent")
                expected_length = end - start + 1
                if len(response.content) != expected_length:
                    raise ValueError("gridded rainfall byte range is incomplete")
                return response.content

            tasks = [
                asyncio.create_task(fetch_range(start, end))
                for start, end in ranges
            ]
            try:
                chunks = await asyncio.gather(*tasks)
            except Exception:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                raise

            content_type = probe.headers.get("content-type", "text/csv")
            content_type = content_type.rpartition(",")[2]
            content_type = content_type.partition(";")[0].strip() or "text/csv"
            return GriddedRainfallDownload(
                payload=b"".join(chunks),
                etag=etag,
                content_type=content_type,
            )
    except DatasetUpstreamError:
        raise
    except (TimeoutError, ValueError) as error:
        raise DatasetUpstreamError(dataset) from error


def _parse_time(value: str) -> datetime:
    return datetime.strptime(value.strip(), "%Y%m%d%H%M").replace(tzinfo=HONG_KONG)


def parse_gridded_rainfall_csv(
    raw_payload: bytes,
    *,
    minimum_periods: int = 1,
) -> tuple[RainfallGridData, ...]:
    reader = csv.reader(
        io.StringIO(raw_payload.decode("utf-8-sig")),
        strict=True,
    )
    try:
        header = next(reader, None)
        if header is None or tuple(value.strip() for value in header) != (
            GRIDDED_RAINFALL_HEADER
        ):
            raise ValueError("gridded rainfall CSV has an unexpected schema")

        issue_time: datetime | None = None
        points_by_valid_time: dict[
            datetime,
            dict[tuple[float, float], tuple[float, tuple[str, ...]]],
        ] = {}
        for row in reader:
            if not row or all(not value.strip() for value in row):
                continue
            if len(row) != len(GRIDDED_RAINFALL_HEADER):
                raise ValueError("gridded rainfall row has an unexpected schema")

            updated, valid, raw_latitude, raw_longitude, raw_rainfall = row
            row_updated_at = _parse_time(updated)
            row_valid_at = _parse_time(valid)
            try:
                latitude = float(raw_latitude)
                longitude = float(raw_longitude)
                rainfall = float(raw_rainfall)
            except ValueError as error:
                raise ValueError(
                    "gridded rainfall row contains a non-numeric value"
                ) from error
            if not all(
                math.isfinite(value) for value in (latitude, longitude, rainfall)
            ):
                raise ValueError("gridded rainfall row contains a non-finite value")
            if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
                raise ValueError("gridded rainfall coordinate is out of range")
            if rainfall < 0:
                raise ValueError("gridded rainfall value is negative")
            if row_valid_at <= row_updated_at:
                raise ValueError("gridded rainfall valid time is not in the future")

            if issue_time is None:
                issue_time = row_updated_at
            elif row_updated_at != issue_time:
                raise ValueError("gridded rainfall has inconsistent issue times")

            coordinate = (latitude, longitude)
            points = points_by_valid_time.setdefault(row_valid_at, {})
            if coordinate in points:
                raise ValueError("gridded rainfall grid has duplicate coordinates")
            points[coordinate] = (rainfall, tuple(row))
    except csv.Error as error:
        raise ValueError("gridded rainfall CSV is malformed") from error

    valid_times = sorted(points_by_valid_time)
    if issue_time is None or len(valid_times) < minimum_periods:
        raise ValueError("gridded rainfall CSV contains insufficient data")
    if any(
        later - earlier != FORECAST_INTERVAL
        for earlier, later in zip(valid_times, valid_times[1:], strict=False)
    ):
        raise ValueError("gridded rainfall forecast periods are not half-hourly")

    grids = []
    reference_coordinates: set[tuple[float, float]] | None = None
    for valid_time in valid_times:
        points = points_by_valid_time[valid_time]
        coordinates = set(points)
        latitudes = tuple(sorted({point[0] for point in coordinates}, reverse=True))
        longitudes = tuple(sorted({point[1] for point in coordinates}))
        if len(coordinates) != len(latitudes) * len(longitudes):
            raise ValueError("gridded rainfall grid is not rectangular")
        if reference_coordinates is None:
            reference_coordinates = coordinates
        elif coordinates != reference_coordinates:
            raise ValueError("gridded rainfall forecast grids are inconsistent")
        grids.append(
            RainfallGridData(
                updated_at=issue_time,
                valid_at=valid_time,
                latitudes=latitudes,
                longitudes=longitudes,
                values=tuple(
                    points[(latitude, longitude)][0]
                    for latitude in latitudes
                    for longitude in longitudes
                ),
                source_rows=tuple(item[1] for item in points.values()),
            )
        )
    return tuple(grids)


def validate_gridded_rainfall_csv(raw_payload: bytes) -> ValidatedPayload:
    grids = parse_gridded_rainfall_csv(raw_payload, minimum_periods=2)
    selected_grids = grids[:2]
    archive_buffer = io.StringIO(newline="")
    writer = csv.writer(archive_buffer, lineterminator="\n")
    writer.writerow(GRIDDED_RAINFALL_HEADER)
    for grid in selected_grids:
        writer.writerows(grid.source_rows)
    return ValidatedPayload(
        source_updated_at=grids[0].updated_at,
        archive_payload=archive_buffer.getvalue().encode(),
        metadata={
            "archive_valid_times": [grid.valid_at for grid in selected_grids],
        },
    )
