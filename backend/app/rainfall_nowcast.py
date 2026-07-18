import csv
import io
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .ingestion import ValidatedPayload

HONG_KONG = ZoneInfo("Asia/Hong_Kong")
FORECAST_INTERVAL = timedelta(minutes=30)
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
