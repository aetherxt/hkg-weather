from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class PublicModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
    )


class ErrorResponse(PublicModel):
    detail: str | list[dict[str, Any]]


class ResponseMetadata(PublicModel):
    dataset: str
    source_updated_at: datetime | None
    fetched_at: datetime | None


class ListResponseMetadata(ResponseMetadata):
    count: int


class DataResponse[Data](PublicModel):
    data: Data
    meta: ResponseMetadata


class ListResponse[Item](PublicModel):
    data: list[Item]
    meta: ListResponseMetadata


class WarningsData(PublicModel):
    summary: dict[str, Any]
    information: dict[str, Any]
    special_weather_tips: dict[str, Any]


class TemperatureReading(PublicModel):
    observed_at: datetime
    station: str
    temperature_c: float | None


class WindReading(PublicModel):
    observed_at: datetime
    station: str
    mean_wind_direction: str | None
    mean_wind_speed_kmh: float | None
    maximum_gust_kmh: float | None


class LamppostReading(PublicModel):
    lamppost_id: str
    device_id: str
    label: str
    latitude: float
    longitude: float
    reading: dict[str, Any]


class StationItem(PublicModel):
    station_code: str
    label: str


class ModelItem(PublicModel):
    model_id: str
    label: str
    rainfall_interval_hours: int | None
    maximum_lead_hours: int | None
    current_cycle: datetime | None
    cycle_fetched_at: datetime | None


class Bounds(PublicModel):
    north: float
    south: float
    east: float
    west: float


class RainfallGrid(PublicModel):
    updated_at: datetime
    valid_at: datetime
    bounds: Bounds
    width: int
    height: int
    values: list[float]


class RainfallFrame(PublicModel):
    updated_at: datetime
    valid_at: datetime
    bounds: Bounds
    width: int
    height: int
    url: str


class RadarMetadata(PublicModel):
    observed_at: datetime
    bounds: Bounds
    width: int
    height: int
    image_url: str


class ModelRainfallMetadata(PublicModel):
    model_id: str
    label: str
    cycle: datetime
    lead_hours: int
    valid_at: datetime
    width: int
    height: int
    image_url: str


class ModelWindMetadata(PublicModel):
    model_id: str
    label: str
    cycle: datetime
    lead_hours: int
    valid_at: datetime
    level: str
    components: list[str]
    units: str
    encoded_width: int
    encoded_height: int
    header_rows: int
    grid_width: int
    grid_height: int
    image_url: str


class TropicalCyclone(PublicModel):
    storm_id: str
    name_en: str
    name_zh: str
    fetched_at: datetime
    geo_json: dict[str, Any]
    potential_track_area_geo_json: dict[str, Any] | None


class ArchivedTropicalCyclone(PublicModel):
    storm_id: str
    name_en: str
    name_zh: str
    fetched_at: datetime
    geo_json: dict[str, Any]
    potential_track_area_geo_json: dict[str, Any] | None


class AstronomicalTimes(PublicModel):
    date: str
    sunrise: str
    sun_transit: str
    sunset: str
    moonrise: str | None
    moon_transit: str | None
    moonset: str | None


class DashboardSnapshot(PublicModel):
    warnings: DataResponse[WarningsData] | None
    current: DataResponse[dict[str, Any]] | None
    local_forecast: DataResponse[dict[str, Any]] | None
    nine_day_forecast: DataResponse[dict[str, Any]] | None
    regional_temperature: ListResponse[TemperatureReading] | None
    regional_wind: ListResponse[WindReading] | None
    lampposts: ListResponse[LamppostReading] | None
    astronomical: DataResponse[AstronomicalTimes] | None
    station_rainfall: DataResponse[dict[str, Any]] | None


class ArchivedObservation(PublicModel):
    source_updated_at: datetime | None
    fetched_at: datetime
    observation: dict[str, Any]


class ArchivedRainfallFrame(PublicModel):
    issue_time: datetime
    valid_time: datetime
    url: str


class ArchivedRadarFrame(PublicModel):
    observed_at: datetime
    bounds: Bounds
    width: int
    height: int
    image_url: str


class ArchivedForecast(PublicModel):
    source_updated_at: datetime | None
    fetched_at: datetime
    forecast: dict[str, Any]


class ArchivedModelRainfall(PublicModel):
    cycle: datetime
    valid_at: datetime
    lead_hours: int
    width: int
    height: int
    image_url: str


class ArchivedModelWind(PublicModel):
    cycle: datetime
    valid_at: datetime
    lead_hours: int
    level: str
    encoded_width: int
    encoded_height: int
    header_rows: int
    grid_width: int
    grid_height: int
    image_url: str
