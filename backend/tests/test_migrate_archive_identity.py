import asyncio
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.storage import ArchivePolicy
from scripts.migrate_archive_identity import (
    ArchiveMigrationPlan,
    apply_migration,
    build_migration_plan,
    infer_archive_policy,
    infer_document_id,
)


@pytest.mark.parametrize(
    ("document", "expected"),
    [
        (
            {
                "dataset": "ocf_station_forecast",
                "payload": json.dumps({"StationCode": "hko"}).encode(),
            },
            "ocf_station_forecast:HKO",
        ),
        (
            {
                "dataset": "smart_lamppost",
                "payload": json.dumps({"PI": "50148", "DI": "01"}).encode(),
            },
            "smart_lamppost:50148:01",
        ),
        (
            {"dataset": "earth_weather_rainfall", "model": "ec"},
            "earth_weather_rainfall:ec",
        ),
        (
            {"dataset": "tropical_cyclone_track", "storm_id": "2501"},
            "tropical_cyclone_track:2501",
        ),
        (
            {"dataset": "current_weather"},
            "current_weather",
        ),
    ],
)
def test_document_id_is_inferred_for_legacy_archives(
    document: dict[str, object],
    expected: str,
) -> None:
    assert infer_document_id(document) == expected


def test_existing_document_id_is_preserved() -> None:
    assert infer_document_id(
        {
            "dataset": "current_weather",
            "document_id": "current_weather",
        }
    ) == "current_weather"


def test_plausible_but_incorrect_document_id_is_rebuilt() -> None:
    assert infer_document_id(
        {
            "dataset": "earth_weather_rainfall",
            "document_id": "wrong",
            "model": "ec",
        }
    ) == "earth_weather_rainfall:ec"


@pytest.mark.parametrize("invalid_document_id", ["", "   ", None, 7])
def test_invalid_document_id_is_rebuilt(
    invalid_document_id: object,
) -> None:
    assert infer_document_id(
        {
            "dataset": "current_weather",
            "document_id": invalid_document_id,
        }
    ) == "current_weather"


def test_archive_policy_is_inferred_from_slot_presence() -> None:
    assert infer_archive_policy({}) is ArchivePolicy.CONTENT
    assert infer_archive_policy(
        {"archive_slot": datetime(2026, 7, 18, tzinfo=UTC)}
    ) is ArchivePolicy.SLOT
    assert infer_archive_policy(
        {"archive_policy": "content", "archive_slot": None}
    ) is ArchivePolicy.CONTENT


def test_invalid_existing_archive_policy_is_repaired_from_slot_presence() -> None:
    assert infer_archive_policy(
        {"archive_policy": "unknown"}
    ) is ArchivePolicy.CONTENT
    assert infer_archive_policy(
        {"archive_policy": "unknown", "archive_slot": datetime.now(UTC)}
    ) is ArchivePolicy.SLOT


def test_migration_plan_finds_legacy_documents_and_indexes() -> None:
    payload_cursor = MagicMock()
    payload_cursor.__aiter__.return_value = iter([])
    metadata_cursor = MagicMock()
    metadata_cursor.__aiter__.return_value = iter(
        [
            {"_id": "one", "dataset": "current_weather"},
            {
                "_id": "two",
                "dataset": "radar_128",
                "document_id": "",
                "archive_policy": "invalid",
                "archive_slot": datetime(2026, 7, 18, tzinfo=UTC),
            },
        ]
    )
    archive = MagicMock()
    archive.index_information = AsyncMock(
        return_value={"_id_": {}, "archive_dataset_content_unique": {}}
    )
    archive.find.side_effect = [payload_cursor, metadata_cursor]
    database = MagicMock()
    database.__getitem__.return_value = archive

    plan = asyncio.run(build_migration_plan(database))

    assert plan.scanned_documents == 2
    assert plan.document_ids_to_set == 2
    assert plan.policies_to_set == 2
    assert len(plan.updates) == 2
    assert plan.legacy_indexes == ("archive_dataset_content_unique",)
    assert archive.find.call_count == 2
    assert archive.find.call_args_list[1].args[0] == {}


def test_migration_compares_payload_derived_document_ids() -> None:
    payload_cursor = MagicMock()
    payload_cursor.__aiter__.return_value = iter(
        [
            {
                "_id": "ocf",
                "dataset": "ocf_station_forecast",
                "payload": json.dumps({"StationCode": "HKO"}).encode(),
            }
        ]
    )
    metadata_cursor = MagicMock()
    metadata_cursor.__aiter__.return_value = iter(
        [
            {
                "_id": "ocf",
                "dataset": "ocf_station_forecast",
                "document_id": "wrong",
                "archive_policy": "content",
            }
        ]
    )
    archive = MagicMock()
    archive.index_information = AsyncMock(return_value={})
    archive.find.side_effect = [payload_cursor, metadata_cursor]
    database = MagicMock()
    database.__getitem__.return_value = archive

    plan = asyncio.run(build_migration_plan(database))

    assert plan.document_ids_to_set == 1
    assert plan.policies_to_set == 0
    assert len(plan.updates) == 1


def test_migration_creates_replacement_indexes_before_dropping_legacy() -> None:
    archive = MagicMock()
    archive.create_index = AsyncMock()
    archive.drop_index = AsyncMock()
    archive.bulk_write = AsyncMock()
    database = MagicMock()
    database.__getitem__.return_value = archive
    plan = ArchiveMigrationPlan(
        scanned_documents=0,
        updates=(),
        document_ids_to_set=0,
        policies_to_set=0,
        legacy_indexes=("archive_dataset_content_unique",),
    )

    asyncio.run(apply_migration(database, plan))

    archive.bulk_write.assert_not_awaited()
    assert archive.create_index.await_count == 6
    archive.drop_index.assert_awaited_once_with(
        "archive_dataset_content_unique"
    )
