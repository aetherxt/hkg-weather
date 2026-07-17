import asyncio
import struct
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app import internal_feeds
from app.internal_feeds import (
    EARTH_WEATHER_MODELS,
    EARTH_WEATHER_RAINFALL_MODELS,
    EarthWeatherCyclePayload,
    OcfStationForecastPayload,
    earth_cycle_source_updated_at,
    earth_rainfall_lead_hours,
    earth_weather_cycle_spec,
    earth_weather_rainfall_spec,
    load_ocf_stations,
    ocf_source_updated_at,
    ocf_station_spec,
    parse_radar_index,
    parse_tropical_cyclone_index,
    validate_png,
)
from app.json_ingestion import JsonIngestionResult


def test_ocf_station_configuration_and_source_time() -> None:
    stations = load_ocf_stations()

    assert [station.station_code for station in stations] == [
        "CCH",
        "HKA",
        "HKO",
        "HKS",
        "JKB",
        "LFS",
        "PEN",
        "SEK",
        "SHA",
        "SKG",
        "SSH",
        "TKL",
        "TPO",
        "TUN",
        "TY1",
        "WGL",
    ]
    spec = ocf_station_spec(stations[2])
    assert spec.document_id == "ocf_station_forecast:HKO"
    assert spec.url.endswith("/HKO.xml")
    assert spec.archive_retention is not None

    payload = OcfStationForecastPayload.model_validate(
        {
            "LastModified": 20260717211202,
            "StationCode": "HKO",
            "Latitude": 22.302,
            "Longitude": 114.174,
            "ModelTime": 2026071612,
            "DailyForecast": [
                {
                    "ForecastDate": "20260718",
                    "ForecastChanceOfRain": "80%",
                }
            ],
            "HourlyWeatherForecast": [
                {
                    "ForecastHour": "2026071800",
                    "ForecastTemperature": 27.0,
                }
            ],
        }
    )

    assert ocf_source_updated_at(payload) == datetime.fromisoformat(
        "2026-07-17T21:12:02+08:00"
    )


def test_ocf_station_ingestion_has_bounded_concurrency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_requests = 0
    maximum_active_requests = 0

    async def fake_ingest_json_dataset(
        database: object,
        client: object,
        spec: object,
    ) -> JsonIngestionResult:
        nonlocal active_requests, maximum_active_requests
        active_requests += 1
        maximum_active_requests = max(maximum_active_requests, active_requests)
        await asyncio.sleep(0)
        active_requests -= 1
        return JsonIngestionResult(
            changed=True,
            source_updated_at=datetime(2026, 7, 17, tzinfo=UTC),
            fetched_at=datetime(2026, 7, 17, 1, tzinfo=UTC),
        )

    monkeypatch.setattr(
        internal_feeds,
        "ingest_json_dataset",
        fake_ingest_json_dataset,
    )

    results = asyncio.run(
        internal_feeds.ingest_ocf_station_forecasts(
            object(),
            object(),
            load_ocf_stations(),
        )
    )

    assert len(results) == 16
    assert maximum_active_requests == 4
    assert [result.dataset for result in results[:3]] == [
        "ocf_station_forecast:CCH",
        "ocf_station_forecast:HKA",
        "ocf_station_forecast:HKO",
    ]


def test_earth_weather_cycle_specs_are_latest_only() -> None:
    assert [model.model_id for model in EARTH_WEATHER_MODELS] == [
        "ec",
        "aifs",
        "fengwu_ec",
        "fuxi_ec",
        "pangu_ec",
        "aamc",
    ]

    spec = earth_weather_cycle_spec(EARTH_WEATHER_MODELS[0])
    assert spec.document_id == "earth_weather_model_cycle:ec"
    assert spec.url.endswith("/current_ec.json")
    assert spec.archive_retention is None

    payload = EarthWeatherCyclePayload.model_validate(
        {"default": "2026071700", "tc_track": None}
    )
    assert earth_cycle_source_updated_at(payload) == datetime(
        2026,
        7,
        17,
        tzinfo=UTC,
    )


def test_earth_weather_rainfall_spec_uses_latest_available_frame() -> None:
    model = EARTH_WEATHER_RAINFALL_MODELS[0]
    base_time = datetime(2026, 7, 17, tzinfo=UTC)
    now = datetime(2026, 7, 17, 14, 45, tzinfo=UTC)

    lead_hours = earth_rainfall_lead_hours(model, base_time, now)
    spec = earth_weather_rainfall_spec(model, base_time, lead_hours)

    assert lead_hours == 15
    assert spec.document_id == "earth_weather_rainfall:ec"
    assert spec.url.endswith(
        "/ec_2026071700_2026071715_f015_sfc_RF.png"
    )
    assert spec.archive_retention is not None


def test_png_validation_returns_dimensions_and_metadata() -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(
        ">II", 191, 125
    )
    source_time = datetime(2026, 7, 17, tzinfo=UTC)

    result = validate_png(
        png,
        source_updated_at=source_time,
        metadata={"model": "ec"},
    )

    assert result.source_updated_at == source_time
    assert result.metadata == {
        "model": "ec",
        "raster_width": 191,
        "raster_height": 125,
    }


def test_radar_index_selects_latest_frame_and_bounds() -> None:
    kml = b"""<?xml version="1.0"?>
    <kml xmlns="http://www.opengis.net/kml/2.2"><Document>
      <GroundOverlay><Icon><href>20260717221801_rad_128.png</href></Icon>
        <LatLonBox><north>23.4</north><south>21.1</south>
          <east>115.4</east><west>112.9</west></LatLonBox></GroundOverlay>
      <GroundOverlay><Icon><href>20260717222401_rad_128.png</href></Icon>
        <LatLonBox><north>23.5</north><south>21.2</south>
          <east>115.5</east><west>113.0</west></LatLonBox></GroundOverlay>
    </Document></kml>"""

    overlay = parse_radar_index(kml)

    assert overlay.image_url.endswith("/20260717222401_rad_128.png")
    assert overlay.observed_at == datetime.fromisoformat(
        "2026-07-17T22:24:01+08:00"
    )
    assert overlay.bounds == {
        "north": 23.5,
        "south": 21.2,
        "east": 115.5,
        "west": 113.0,
    }


def test_tropical_cyclone_index_handles_inactive_and_active_states() -> None:
    assert parse_tropical_cyclone_index(b"NIL\n") == []

    cyclones = parse_tropical_cyclone_index(
        'var tc = ["2601,ALPHA,\u963f\u723e\u6cd5"];'.encode()
    )

    assert len(cyclones) == 1
    assert cyclones[0].storm_id == "2601"
    assert cyclones[0].english_name == "ALPHA"


def test_inactive_tropical_cyclone_removes_stale_latest_tracks() -> None:
    response = httpx.Response(
        200,
        content=b"NIL",
        request=httpx.Request("GET", "https://example.test/tc-list.js"),
    )
    client = MagicMock()
    client.get = AsyncMock(return_value=response)
    latest = MagicMock()
    latest.delete_many = AsyncMock()
    database = MagicMock()
    database.__getitem__.return_value = latest

    results = asyncio.run(
        internal_feeds.ingest_tropical_cyclone_tracks(database, client)
    )

    assert results == []
    latest.delete_many.assert_awaited_once_with(
        {
            "dataset": "tropical_cyclone_track",
            "_id": {"$nin": []},
        }
    )
