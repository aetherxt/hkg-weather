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
            "dataset": "ocf_station_forecast",
            "document_id": "ocf_station_forecast:HKO",
        }
    ) == "ocf_station_forecast:HKO"


def test_archive_policy_is_inferred_from_slot_presence() -> None:
    assert infer_archive_policy({}) is ArchivePolicy.CONTENT
    assert infer_archive_policy(
        {"archive_slot": datetime(2026, 7, 18, tzinfo=UTC)}
    ) is ArchivePolicy.SLOT
    assert infer_archive_policy(
        {"archive_policy": "content", "archive_slot": None}
    ) is ArchivePolicy.CONTENT


def test_invalid_existing_archive_policy_is_rejected() -> None:
    with pytest.raises(ValueError, match="invalid archive_policy"):
        infer_archive_policy({"archive_policy": "unknown"})


def test_migration_plan_finds_legacy_documents_and_indexes() -> None:
    cursor = MagicMock()
    cursor.__aiter__.return_value = iter(
        [{"_id": "one", "dataset": "current_weather"}]
    )
    archive = MagicMock()
    archive.index_information = AsyncMock(
        return_value={"_id_": {}, "archive_dataset_content_unique": {}}
    )
    archive.find.return_value = cursor
    database = MagicMock()
    database.__getitem__.return_value = archive

    plan = asyncio.run(build_migration_plan(database))

    assert plan.scanned_documents == 1
    assert plan.document_ids_to_add == 1
    assert plan.policies_to_add == 1
    assert len(plan.updates) == 1
    assert plan.legacy_indexes == ("archive_dataset_content_unique",)


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
        document_ids_to_add=0,
        policies_to_add=0,
        legacy_indexes=("archive_dataset_content_unique",),
    )

    asyncio.run(apply_migration(database, plan))

    archive.bulk_write.assert_not_awaited()
    assert archive.create_index.await_count == 6
    archive.drop_index.assert_awaited_once_with(
        "archive_dataset_content_unique"
    )
