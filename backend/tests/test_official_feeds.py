import json
from datetime import datetime

from app.official_feeds import (
    GRIDDED_RAINFALL_SPEC,
    LOCAL_FORECAST_SPEC,
    SPECIAL_WEATHER_TIPS_SPEC,
    WARNING_SUMMARY_SPEC,
    load_smart_lamppost_devices,
    smart_lamppost_spec,
    validate_gridded_rainfall_csv,
    validate_temperature_csv,
    validate_wind_csv,
)


def test_official_json_specs_extract_source_times_and_retention() -> None:
    local = LOCAL_FORECAST_SPEC.payload_model.model_validate_json(
        json.dumps({"updateTime": "2026-07-17T18:45:00+08:00"})
    )
    assert LOCAL_FORECAST_SPEC.source_updated_at(local) == datetime.fromisoformat(
        "2026-07-17T18:45:00+08:00"
    )
    assert LOCAL_FORECAST_SPEC.archive_retention is not None

    warning_summary = WARNING_SUMMARY_SPEC.payload_model.model_validate_json("{}")
    assert WARNING_SUMMARY_SPEC.source_updated_at(warning_summary) is None
    assert WARNING_SUMMARY_SPEC.archive_retention is None

    tips = SPECIAL_WEATHER_TIPS_SPEC.payload_model.model_validate_json('{"swt": []}')
    assert SPECIAL_WEATHER_TIPS_SPEC.source_updated_at(tips) is None
    assert SPECIAL_WEATHER_TIPS_SPEC.archive_retention is None


def test_gridded_rainfall_archive_keeps_first_two_forecast_periods() -> None:
    raw = (
        b"Updated Date and Time (in Hong Kong Time),"
        b"Ending Date and Time (in Hong Kong Time),Latitude (degree),"
        b"Longitude (degree),Half-hourly Nowcast Accumulated Rainfall (mm)\n"
        b"202607171800,202607171830,22.1,114.1,1.0\n"
        b"202607171800,202607171830,22.2,114.2,2.0\n"
        b"202607171800,202607171900,22.1,114.1,3.0\n"
        b"202607171800,202607171930,22.1,114.1,4.0\n"
    )

    validated = validate_gridded_rainfall_csv(raw)
    archived = validated.archive_payload.decode() if validated.archive_payload else ""

    assert validated.source_updated_at == datetime.fromisoformat(
        "2026-07-17T18:00:00+08:00"
    )
    assert "202607171830" in archived
    assert "202607171900" in archived
    assert "202607171930" not in archived
    assert validated.metadata["archive_valid_times"] == [
        datetime.fromisoformat("2026-07-17T18:30:00+08:00"),
        datetime.fromisoformat("2026-07-17T19:00:00+08:00"),
    ]
    assert GRIDDED_RAINFALL_SPEC.archive_interval is not None


def test_regional_temperature_csv_extracts_hong_kong_time() -> None:
    validated = validate_temperature_csv(
        b"Date time,Automatic Weather Station,Air Temperature(degree Celsius)\n"
        b"202607171820,Chek Lap Kok,29.1\n"
    )

    assert validated.source_updated_at == datetime.fromisoformat(
        "2026-07-17T18:20:00+08:00"
    )


def test_regional_wind_csv_accepts_hko_calm_row_anomaly() -> None:
    validated = validate_wind_csv(
        b"Date time,Automatic Weather Station,Direction,Speed,Gust\n"
        b"202607181330,Central Pier,Northwest,9,14\n"
        b"202607181330,Lamma Island,Calm,Calm,0,\n"
    )

    assert validated.source_updated_at == datetime.fromisoformat(
        "2026-07-18T13:30:00+08:00"
    )


def test_smart_lamppost_configuration_builds_separate_documents() -> None:
    devices = load_smart_lamppost_devices()

    assert [(device.lamppost_id, device.device_id) for device in devices] == [
        ("50148", "01"),
        ("27357", "01"),
        ("AB3301", "01"),
        ("DF3644", "01"),
    ]
    spec = smart_lamppost_spec(devices[0])
    assert spec.document_id == "smart_lamppost:50148:01"
    assert "pi=50148" in spec.url
    assert "di=01" in spec.url
