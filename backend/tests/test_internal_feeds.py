import asyncio
import struct
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, call

import httpx
import pytest

from app import internal_feeds
from app.internal_feeds import (
    EARTH_WEATHER_MODELS,
    EARTH_WEATHER_RAINFALL_MODELS,
    EARTH_WEATHER_WIND_MODELS,
    EarthWeatherCyclePayload,
    OcfStationForecastPayload,
    earth_cycle_source_updated_at,
    earth_rainfall_lead_hours,
    earth_rainfall_leads,
    earth_weather_cycle_spec,
    earth_weather_rainfall_spec,
    earth_weather_wind_spec,
    load_ocf_stations,
    ocf_source_updated_at,
    ocf_station_spec,
    parse_radar_index,
    parse_tropical_cyclone_index,
    validate_png,
)
from app.json_ingestion import JsonDatasetUpstreamError, JsonIngestionResult
from app.raw_ingestion import RawIngestionResult


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


def test_earth_weather_cycle_must_be_calendar_valid() -> None:
    with pytest.raises(ValueError):
        EarthWeatherCyclePayload.model_validate({"default": "2026130100"})


def test_rainfall_cycle_conversion_error_is_an_upstream_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def invalid_cycle(*_: object) -> EarthWeatherCyclePayload:
        return EarthWeatherCyclePayload.model_construct(default="2026130100")

    monkeypatch.setattr(
        internal_feeds,
        "_fetch_earth_weather_cycle",
        invalid_cycle,
    )

    with pytest.raises(JsonDatasetUpstreamError) as error:
        asyncio.run(
            internal_feeds.ingest_earth_weather_rainfall(
                object(),
                object(),
                models=(EARTH_WEATHER_RAINFALL_MODELS[0],),
                now=datetime(2026, 7, 18, tzinfo=UTC),
            )
        )

    assert error.value.dataset == "earth_weather_model_cycle"
    assert isinstance(error.value.__cause__, ValueError)


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


def test_earth_weather_rainfall_leads_cover_the_configured_forecast() -> None:
    assert list(earth_rainfall_leads(EARTH_WEATHER_RAINFALL_MODELS[0])) == list(
        range(3, 121, 3)
    )
    assert list(earth_rainfall_leads(EARTH_WEATHER_RAINFALL_MODELS[1])) == list(
        range(6, 121, 6)
    )


def test_earth_weather_wind_spec_uses_ecmwf_surface_uv_frame() -> None:
    model = EARTH_WEATHER_WIND_MODELS[0]
    base_time = datetime(2026, 7, 17, tzinfo=UTC)

    spec = earth_weather_wind_spec(model, base_time, 15)

    assert [item.model_id for item in EARTH_WEATHER_WIND_MODELS] == ["ec"]
    assert spec.document_id == "earth_weather_wind:ec"
    assert spec.url.endswith("/ec_2026071700_2026071715_f015_sfc_UV.png")
    assert spec.archive_retention is not None

    png = (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\rIHDR"
        + struct.pack(">II", 381, 245)
        + bytes((8, 6, 0, 0, 0))
    )
    validated = spec.validate(png)
    assert validated.metadata["raster_width"] == 381
    assert validated.metadata["raster_height"] == 245
    assert validated.metadata["header_rows"] == 4
    assert validated.metadata["grid_width"] == 381
    assert validated.metadata["grid_height"] == 241
    assert validated.metadata["components"] == ["u", "v"]
    assert validated.metadata["units"] == "m/s"


def test_earth_weather_wind_rejects_non_rgba_png() -> None:
    spec = earth_weather_wind_spec(
        EARTH_WEATHER_WIND_MODELS[0],
        datetime(2026, 7, 17, tzinfo=UTC),
        15,
    )
    png = (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\rIHDR"
        + struct.pack(">II", 381, 245)
        + bytes((8, 2, 0, 0, 0))
    )

    with pytest.raises(ValueError, match="8-bit RGBA"):
        spec.validate(png)


def test_earth_weather_rainfall_ingestion_also_stores_ecmwf_wind(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cycle = EarthWeatherCyclePayload(default="2026071700")
    monkeypatch.setattr(
        internal_feeds,
        "_fetch_earth_weather_cycle",
        AsyncMock(return_value=cycle),
    )
    stored = RawIngestionResult(
        changed=True,
        source_updated_at=datetime(2026, 7, 17, tzinfo=UTC),
        fetched_at=datetime(2026, 7, 17, 14, 46, tzinfo=UTC),
    )
    ingest = AsyncMock(return_value=stored)
    monkeypatch.setattr(internal_feeds, "ingest_raw_dataset", ingest)

    results = asyncio.run(
        internal_feeds.ingest_earth_weather_rainfall(
            object(),
            object(),
            models=(EARTH_WEATHER_WIND_MODELS[0],),
            now=datetime(2026, 7, 17, 14, 45, tzinfo=UTC),
        )
    )

    assert len(results) == 80
    assert sum(
        result.dataset == "earth_weather_rainfall:ec" for result in results
    ) == 40
    assert sum(result.dataset == "earth_weather_wind:ec" for result in results) == 40
    assert ingest.await_args_list[0].args[2].url.endswith(
        "_2026071703_f003_sfc_RF.png"
    )
    assert ingest.await_args_list[1].args[2].url.endswith(
        "_2026071703_f003_sfc_UV.png"
    )
    assert ingest.await_args_list[-2].args[2].url.endswith(
        "_2026072200_f120_sfc_RF.png"
    )
    assert ingest.await_args_list[-1].args[2].url.endswith(
        "_2026072200_f120_sfc_UV.png"
    )


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
    assert parse_tropical_cyclone_index(b"var tc=[];\n") == []

    cyclones = parse_tropical_cyclone_index(
        'var tc = ["2601,ALPHA,\u963f\u723e\u6cd5"];'.encode()
    )

    assert len(cyclones) == 1
    assert cyclones[0].storm_id == "2601"
    assert cyclones[0].english_name == "ALPHA"


def test_tropical_cyclone_index_handles_indexed_assignments() -> None:
    cyclones = parse_tropical_cyclone_index(
        (
            'var tc=[];\n'
            'tc[1]="2618,BETA,\u8c9d\u5854";\n'
            'tc[0]="2617,Tropical Depression,\u71b1\u5e36\u4f4e\u6c23\u58d3";\n'
        ).encode()
    )

    assert [
        (cyclone.storm_id, cyclone.english_name, cyclone.chinese_name)
        for cyclone in cyclones
    ] == [
        ("2617", "Tropical Depression", "\u71b1\u5e36\u4f4e\u6c23\u58d3"),
        ("2618", "BETA", "\u8c9d\u5854"),
    ]


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
    assert latest.delete_many.await_args_list == [
        call(
            {
                "dataset": "tropical_cyclone_track",
                "_id": {"$nin": []},
            }
        ),
        call(
            {
                "dataset": "tropical_cyclone_track_area",
                "_id": {"$nin": []},
            }
        ),
    ]


def test_tropical_cyclone_index_fetch_retries_server_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failed_response = httpx.Response(
        502,
        request=httpx.Request("GET", "https://example.test/tc-list.js"),
    )
    successful_response = httpx.Response(
        200,
        content=b"NIL",
        request=httpx.Request("GET", "https://example.test/tc-list.js"),
    )
    client = MagicMock()
    client.get = AsyncMock(side_effect=[failed_response, successful_response])
    latest = MagicMock()
    latest.delete_many = AsyncMock()
    database = MagicMock()
    database.__getitem__.return_value = latest
    sleep = AsyncMock()
    monkeypatch.setattr("app.ingestion.asyncio.sleep", sleep)

    results = asyncio.run(
        internal_feeds.ingest_tropical_cyclone_tracks(database, client)
    )

    assert results == []
    assert client.get.await_count == 2
    sleep.assert_awaited_once_with(1.0)


def test_tropical_cyclone_track_area_requires_filled_forecast_polygon() -> None:
    cyclone = internal_feeds.ActiveTropicalCyclone(
        storm_id="2601",
        english_name="ALPHA",
        chinese_name="阿爾法",
    )
    valid = b"""<kml xmlns="http://earth.google.com/kml/2.2"><Document>
      <Placemark><styleUrl>#error_cone_0_</styleUrl><Polygon>
        <outerBoundaryIs><LinearRing><coordinates>
          114,22,0 115,22,0 115,23,0 114,22,0
        </coordinates></LinearRing></outerBoundaryIs>
      </Polygon></Placemark>
      <Placemark><styleUrl>#circles</styleUrl><Polygon>
        <outerBoundaryIs><LinearRing><coordinates>
          114,22,0 115,22,0 115,23,0 114,22,0
        </coordinates></LinearRing></outerBoundaryIs>
      </Polygon></Placemark>
    </Document></kml>"""

    validated = internal_feeds.validate_tropical_cyclone_track_area(
        valid,
        cyclone,
    )

    assert validated.metadata["forecast_periods"] == ["0-72"]
    assert validated.metadata["storm_id"] == "2601"
    assert internal_feeds.tropical_cyclone_track_area_available(valid) is True
    assert (
        internal_feeds.tropical_cyclone_track_area_available(
            valid.replace(b"#error_cone_0_", b"#circles")
        )
        is False
    )
    with pytest.raises(ValueError, match="no forecast polygons"):
        internal_feeds.validate_tropical_cyclone_track_area(
            valid.replace(b"#error_cone_0_", b"#circles"),
            cyclone,
        )


def test_tropical_cyclone_ingests_track_and_potential_area(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = httpx.Response(
        200,
        content=b'var tc=["2601,ALPHA,ALPHA ZH"];',
        request=httpx.Request("GET", "https://example.test/tc-list.js"),
    )
    track = httpx.Response(
        200,
        content=b"<kml><Placemark><Point><coordinates>114,22</coordinates>"
        b"</Point></Placemark></kml>",
        request=httpx.Request("GET", "https://example.test/track.xml"),
    )
    area = httpx.Response(
        200,
        content=b"<kml><Placemark><styleUrl>#error_cone_0_</styleUrl>"
        b"<Polygon><outerBoundaryIs><LinearRing><coordinates>"
        b"114,22 115,22 115,23 114,22"
        b"</coordinates></LinearRing></outerBoundaryIs></Polygon>"
        b"</Placemark></kml>",
        request=httpx.Request("GET", "https://example.test/area.kml"),
    )
    client = MagicMock()
    client.get = AsyncMock(side_effect=[index, track, area])
    latest = MagicMock()
    latest.delete_many = AsyncMock()
    database = MagicMock()
    database.__getitem__.return_value = latest
    ingested = RawIngestionResult(
        changed=True,
        source_updated_at=None,
        fetched_at=datetime(2026, 7, 23, tzinfo=UTC),
    )
    ingest = AsyncMock(return_value=ingested)
    monkeypatch.setattr(internal_feeds, "ingest_raw_dataset", ingest)

    results = asyncio.run(
        internal_feeds.ingest_tropical_cyclone_tracks(database, client)
    )

    assert [result.dataset for result in results] == [
        "tropical_cyclone_track:2601",
        "tropical_cyclone_track_area:2601",
    ]
    assert ingest.await_count == 2
    assert ingest.await_args_list[0].args[2].dataset == "tropical_cyclone_track"
    assert (
        ingest.await_args_list[1].args[2].dataset
        == "tropical_cyclone_track_area"
    )


def test_missing_tropical_cyclone_track_area_does_not_fail_track(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = httpx.Response(
        200,
        content=b'var tc=["2601,ALPHA,ALPHA ZH"];',
        request=httpx.Request("GET", "https://example.test/tc-list.js"),
    )
    track = httpx.Response(
        200,
        content=b"<kml><coordinates>114,22</coordinates></kml>",
        request=httpx.Request("GET", "https://example.test/track.xml"),
    )
    missing_area = httpx.Response(
        404,
        request=httpx.Request("GET", "https://example.test/area.kml"),
    )
    client = MagicMock()
    client.get = AsyncMock(side_effect=[index, track, missing_area])
    latest = MagicMock()
    latest.delete_one = AsyncMock()
    latest.delete_many = AsyncMock()
    database = MagicMock()
    database.__getitem__.return_value = latest
    ingested = RawIngestionResult(
        changed=True,
        source_updated_at=None,
        fetched_at=datetime(2026, 7, 23, tzinfo=UTC),
    )
    ingest = AsyncMock(return_value=ingested)
    monkeypatch.setattr(internal_feeds, "ingest_raw_dataset", ingest)

    results = asyncio.run(
        internal_feeds.ingest_tropical_cyclone_tracks(database, client)
    )

    assert [result.dataset for result in results] == [
        "tropical_cyclone_track:2601"
    ]
    latest.delete_one.assert_awaited_once_with(
        {"_id": "tropical_cyclone_track_area:2601"}
    )
