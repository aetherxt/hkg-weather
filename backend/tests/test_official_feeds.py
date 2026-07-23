import asyncio
import json
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from app import official_feeds
from app.ingestion import DatasetIngestionResult
from app.official_feeds import (
    GRIDDED_RAINFALL_SPEC,
    LOCAL_FORECAST_SPEC,
    SPECIAL_WEATHER_TIPS_SPEC,
    WARNING_SUMMARY_SPEC,
    WIND_CSV_HEADER,
    SmartLamppostObservation,
    astronomical_times_specs,
    ingest_gridded_rainfall,
    load_smart_lamppost_devices,
    smart_lamppost_spec,
    validate_astronomical_times_csv,
    validate_gridded_rainfall_csv,
    validate_temperature_csv,
    validate_wind_csv,
)
from app.rainfall_nowcast import (
    GRIDDED_RAINFALL_HEADER,
    GriddedRainfallDownload,
)
from app.storage import ArchivePolicy

GRIDDED_RAINFALL_HEADER_TEXT = ",".join(GRIDDED_RAINFALL_HEADER) + "\n"
GRIDDED_RAINFALL_HEADER_BYTES = GRIDDED_RAINFALL_HEADER_TEXT.encode()
WIND_HEADER_TEXT = ",".join(WIND_CSV_HEADER) + "\n"
WIND_HEADER_BYTES = WIND_HEADER_TEXT.encode()


def astronomical_csv(
    year: int,
    *,
    moon: bool = False,
    replace: tuple[date, str] | None = None,
) -> bytes:
    lines = ["YYYY-MM-DD,RISE,TRAN.,SET"]
    current = date(year, 1, 1)
    end = date(year + 1, 1, 1)
    while current < end:
        values = "06:30,12:15,18:00"
        if moon and current.day == 3:
            values = "17:41,,06:50"
        if replace is not None and current == replace[0]:
            values = replace[1]
        lines.append(f"{current.isoformat()},{values}")
        current += timedelta(days=1)
    return ("\n".join(lines) + "\n").encode()


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


def test_astronomical_specs_use_selected_year_and_latest_only() -> None:
    solar, lunar = astronomical_times_specs(2028)

    assert "dataType=SRS" in solar.url
    assert "year=2028" in solar.url
    assert "dataType=MRS" in lunar.url
    assert solar.archive_retention is None
    assert lunar.archive_retention is None


def test_astronomical_csv_validates_complete_year_and_lunar_blanks() -> None:
    solar = validate_astronomical_times_csv(
        astronomical_csv(2026),
        year=2026,
        allow_missing_times=False,
    )
    lunar = validate_astronomical_times_csv(
        astronomical_csv(2028, moon=True),
        year=2028,
        allow_missing_times=True,
    )

    assert solar.metadata == {"year": 2026, "row_count": 365}
    assert lunar.metadata == {"year": 2028, "row_count": 366}
    assert solar.source_updated_at is None


def test_astronomical_csv_rejects_missing_date() -> None:
    raw = astronomical_csv(2026).decode().splitlines()
    del raw[10]

    with pytest.raises(ValueError, match="incomplete or out of order"):
        validate_astronomical_times_csv(
            ("\n".join(raw) + "\n").encode(),
            year=2026,
            allow_missing_times=False,
        )


@pytest.mark.parametrize("invalid_time", ["24:00", "6:30", "noon", ""])
def test_solar_astronomical_csv_rejects_invalid_times(invalid_time: str) -> None:
    raw = astronomical_csv(
        2026,
        replace=(date(2026, 1, 2), f"{invalid_time},12:15,18:00"),
    )

    with pytest.raises(ValueError, match="missing time|invalid time"):
        validate_astronomical_times_csv(
            raw,
            year=2026,
            allow_missing_times=False,
        )


def test_gridded_rainfall_archive_keeps_first_two_forecast_periods() -> None:
    raw = GRIDDED_RAINFALL_HEADER_BYTES + (
        b"202607171800,202607171830,22.1,114.1,1.0\n"
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
    assert GRIDDED_RAINFALL_SPEC.archive_policy is ArchivePolicy.SLOT


def test_unchanged_gridded_rainfall_only_refreshes_fetch_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_updated_at = datetime(2026, 7, 23, 5, 30, tzinfo=UTC)
    fetched_at = datetime(2026, 7, 23, 5, 36, tzinfo=UTC)
    latest = MagicMock()
    latest.find_one = AsyncMock(
        return_value={
            "upstream_etag": '"same"',
            "source_updated_at": source_updated_at,
        }
    )
    latest.update_one = AsyncMock()
    database = MagicMock()
    database.__getitem__.return_value = latest
    fetch_download = AsyncMock(return_value=None)
    monkeypatch.setattr(
        official_feeds,
        "fetch_gridded_rainfall_csv",
        fetch_download,
    )

    result = asyncio.run(
        ingest_gridded_rainfall(database, MagicMock(), now=fetched_at)
    )

    assert result == DatasetIngestionResult(
        changed=False,
        source_updated_at=source_updated_at,
        fetched_at=fetched_at,
    )
    assert fetch_download.await_args.kwargs["known_etag"] == '"same"'
    latest.update_one.assert_awaited_once_with(
        {"_id": GRIDDED_RAINFALL_SPEC.document_id},
        {"$set": {"fetched_at": fetched_at}},
    )


def test_changed_gridded_rainfall_stores_etag_with_prefetched_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = GRIDDED_RAINFALL_HEADER_BYTES + (
        b"202607231330,202607231400,22.1,114.1,1.0\n"
        b"202607231330,202607231430,22.1,114.1,2.0\n"
    )
    fetched_at = datetime(2026, 7, 23, 5, 36, tzinfo=UTC)
    latest = MagicMock()
    latest.find_one = AsyncMock(return_value=None)
    database = MagicMock()
    database.__getitem__.return_value = latest
    fetch_download = AsyncMock(
        return_value=GriddedRainfallDownload(
            payload=raw,
            etag='"changed"',
            content_type="text/csv",
        )
    )
    stored_result = DatasetIngestionResult(
        changed=True,
        source_updated_at=datetime(2026, 7, 23, 5, 30, tzinfo=UTC),
        fetched_at=fetched_at,
    )
    ingest_raw = AsyncMock(return_value=stored_result)
    monkeypatch.setattr(
        official_feeds,
        "fetch_gridded_rainfall_csv",
        fetch_download,
    )
    monkeypatch.setattr(official_feeds, "ingest_raw_dataset", ingest_raw)

    result = asyncio.run(
        ingest_gridded_rainfall(database, MagicMock(), now=fetched_at)
    )

    assert result is stored_result
    spec = ingest_raw.await_args.args[2]
    response = ingest_raw.await_args.kwargs["prefetched_response"]
    assert response.content == raw
    assert response.headers["etag"] == '"changed"'
    assert spec.validate(raw).metadata["upstream_etag"] == '"changed"'
    assert ingest_raw.await_args.kwargs["now"] == fetched_at


@pytest.mark.parametrize(
    "invalid_values",
    [
        "NaN,114.1,1.0",
        "22.1,inf,1.0",
        "22.1,114.1,-inf",
    ],
)
def test_gridded_rainfall_rejects_non_finite_values(
    invalid_values: str,
) -> None:
    raw = (
        GRIDDED_RAINFALL_HEADER_TEXT + f"202607171800,202607171830,{invalid_values}\n"
        "202607171800,202607171900,22.1,114.1,1.0\n"
    ).encode()

    with pytest.raises(ValueError, match="non-finite"):
        validate_gridded_rainfall_csv(raw)


def test_gridded_rainfall_requires_one_issue_time() -> None:
    raw = GRIDDED_RAINFALL_HEADER_BYTES + (
        b"202607171800,202607171830,22.1,114.1,1.0\n"
        b"202607171801,202607171900,22.1,114.1,2.0\n"
    )

    with pytest.raises(ValueError, match="inconsistent issue times"):
        validate_gridded_rainfall_csv(raw)


def test_gridded_rainfall_accepts_unordered_forecast_periods() -> None:
    raw = GRIDDED_RAINFALL_HEADER_BYTES + (
        b"202607171800,202607171900,22.1,114.1,1.0\n"
        b"202607171800,202607171830,22.1,114.1,2.0\n"
    )

    validated = validate_gridded_rainfall_csv(raw)

    assert validated.metadata["archive_valid_times"] == [
        datetime.fromisoformat("2026-07-17T18:30:00+08:00"),
        datetime.fromisoformat("2026-07-17T19:00:00+08:00"),
    ]


def test_gridded_rainfall_accepts_interleaved_complete_grids() -> None:
    raw = GRIDDED_RAINFALL_HEADER_BYTES + (
        b"202607171800,202607171830,22.1,114.1,1.0\n"
        b"202607171800,202607171900,22.1,114.1,2.0\n"
        b"202607171800,202607171830,22.1,114.2,3.0\n"
        b"202607171800,202607171900,22.1,114.2,4.0\n"
    )

    validated = validate_gridded_rainfall_csv(raw)

    assert validated.metadata["archive_valid_times"] == [
        datetime.fromisoformat("2026-07-17T18:30:00+08:00"),
        datetime.fromisoformat("2026-07-17T19:00:00+08:00"),
    ]


def test_gridded_rainfall_requires_half_hourly_forecast_periods() -> None:
    raw = GRIDDED_RAINFALL_HEADER_BYTES + (
        b"202607171800,202607171817,22.1,114.1,1.0\n"
        b"202607171800,202607171943,22.1,114.1,2.0\n"
    )

    with pytest.raises(ValueError, match="not half-hourly"):
        validate_gridded_rainfall_csv(raw)


def test_gridded_rainfall_rejects_negative_accumulation() -> None:
    raw = GRIDDED_RAINFALL_HEADER_BYTES + (
        b"202607171800,202607171830,22.1,114.1,-0.1\n"
        b"202607171800,202607171900,22.1,114.1,1.0\n"
    )

    with pytest.raises(ValueError, match="negative"):
        validate_gridded_rainfall_csv(raw)


def test_gridded_rainfall_rejects_duplicate_coordinates() -> None:
    raw = GRIDDED_RAINFALL_HEADER_BYTES + (
        b"202607171800,202607171830,22.1,114.1,1.0\n"
        b"202607171800,202607171830,22.1,114.1,2.0\n"
        b"202607171800,202607171900,22.1,114.1,3.0\n"
    )

    with pytest.raises(ValueError, match="duplicate coordinates"):
        validate_gridded_rainfall_csv(raw)


def test_gridded_rainfall_requires_complete_rectangular_grids() -> None:
    raw = GRIDDED_RAINFALL_HEADER_BYTES + (
        b"202607171800,202607171830,22.1,114.1,1.0\n"
        b"202607171800,202607171830,22.2,114.2,2.0\n"
        b"202607171800,202607171900,22.1,114.1,3.0\n"
        b"202607171800,202607171900,22.2,114.2,4.0\n"
    )

    with pytest.raises(ValueError, match="not rectangular"):
        validate_gridded_rainfall_csv(raw)


def test_regional_temperature_csv_extracts_hong_kong_time() -> None:
    validated = validate_temperature_csv(
        b"Date time,Automatic Weather Station,Air Temperature(degree Celsius)\n"
        b"202607171820,Chek Lap Kok,29.1\n"
    )

    assert validated.source_updated_at == datetime.fromisoformat(
        "2026-07-17T18:20:00+08:00"
    )


def test_regional_temperature_requires_the_documented_header() -> None:
    raw = (
        b"Date time,Air Temperature(degree Celsius),Automatic Weather Station\n"
        b"202607171820,29.1,Chek Lap Kok\n"
    )

    with pytest.raises(ValueError, match="unexpected schema"):
        validate_temperature_csv(raw)


@pytest.mark.parametrize(
    "invalid_row",
    [
        "202607171820,Cheung Chau",
        "202613011820,Cheung Chau,28.0",
        "202607171820,,28.0",
        "202607171820,Cheung Chau,not-a-number",
        "202607171820,Cheung Chau,Calm",
        "202607171821,Cheung Chau,28.0",
    ],
)
def test_regional_temperature_validates_every_row(invalid_row: str) -> None:
    raw = (
        "Date time,Automatic Weather Station,Air Temperature(degree Celsius)\n"
        "202607171820,Chek Lap Kok,29.1\n"
        f"{invalid_row}\n"
    ).encode()

    with pytest.raises(ValueError):
        validate_temperature_csv(raw)


def test_regional_temperature_accepts_supported_missing_values() -> None:
    validated = validate_temperature_csv(
        b"Date time,Automatic Weather Station,Air Temperature(degree Celsius)\n"
        b"202607171820,Chek Lap Kok,N/A\n"
        b"202607171820,Cheung Chau,\n"
    )

    assert validated.source_updated_at == datetime.fromisoformat(
        "2026-07-17T18:20:00+08:00"
    )


def test_regional_wind_csv_accepts_hko_calm_row_anomaly() -> None:
    validated = validate_wind_csv(
        WIND_HEADER_BYTES + b"202607181330,Central Pier,Northwest,9,14\n"
        b"202607181330,Lamma Island,Calm,Calm,0,\n"
    )

    assert validated.source_updated_at == datetime.fromisoformat(
        "2026-07-18T13:30:00+08:00"
    )


@pytest.mark.parametrize(
    "invalid_row",
    [
        "202607181330,Wetland Park,Northwest,fast,14",
        "202607181330,Wetland Park,Northwest,Calm,14",
        "202607181330,Wetland Park,Northwest,9,strong",
        "202607181331,Wetland Park,Northwest,9,14",
        "202607181330,,Northwest,9,14",
    ],
)
def test_regional_wind_validates_every_measurement(invalid_row: str) -> None:
    raw = (
        WIND_HEADER_TEXT + f"202607181330,Central Pier,Northwest,9,14\n{invalid_row}\n"
    ).encode()

    with pytest.raises(ValueError):
        validate_wind_csv(raw)


def test_smart_lamppost_timestamp_must_be_calendar_valid() -> None:
    with pytest.raises(ValidationError):
        SmartLamppostObservation.model_validate({"TS": "20261301000000"})


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
