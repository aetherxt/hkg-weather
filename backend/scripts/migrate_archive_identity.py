from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from typing import Any

from pymongo import UpdateOne
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError

from app.database import close_database_clients, get_ingestion_database
from app.internal_feeds import (
    EARTH_WEATHER_RAINFALL_DATASET,
    OCF_STATION_FORECAST_DATASET,
    TROPICAL_CYCLONE_TRACK_DATASET,
)
from app.official_feeds import SMART_LAMPPOST_DATASET
from app.storage import ArchivePolicy, ensure_storage_indexes

LEGACY_INDEX_NAMES = (
    "archive_dataset_content_unique",
    "archive_dataset_slot_unique",
    "archive_dataset_source_updated",
    "archive_dataset_observed",
    "archive_dataset_model_valid",
)


@dataclass(frozen=True)
class ArchiveMigrationPlan:
    scanned_documents: int
    updates: tuple[UpdateOne, ...]
    document_ids_to_set: int
    policies_to_set: int
    legacy_indexes: tuple[str, ...]


def _json_payload(document: dict[str, Any]) -> dict[str, Any]:
    payload = document.get("payload")
    if not isinstance(payload, bytes):
        raise ValueError("archive payload is not binary JSON")
    try:
        decoded = json.loads(payload)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ValueError("archive payload is invalid JSON") from error
    if not isinstance(decoded, dict):
        raise ValueError("archive JSON payload is not an object")
    return decoded


def infer_document_id(document: dict[str, Any]) -> str:
    dataset = document.get("dataset")
    if not isinstance(dataset, str) or not dataset:
        raise ValueError("archive document has no dataset")

    if dataset == OCF_STATION_FORECAST_DATASET:
        station_code = _json_payload(document).get("StationCode")
        if not isinstance(station_code, str) or not station_code:
            raise ValueError("OCF archive document has no StationCode")
        return f"{dataset}:{station_code.upper()}"

    if dataset == SMART_LAMPPOST_DATASET:
        payload = _json_payload(document)
        lamppost_id = payload.get("PI")
        device_id = payload.get("DI")
        if not isinstance(lamppost_id, str) or not lamppost_id:
            raise ValueError("smart-lamppost archive document has no PI")
        if not isinstance(device_id, str) or not device_id:
            raise ValueError("smart-lamppost archive document has no DI")
        return f"{dataset}:{lamppost_id}:{device_id}"

    if dataset == EARTH_WEATHER_RAINFALL_DATASET:
        model = document.get("model")
        if not isinstance(model, str) or not model:
            raise ValueError("Earth Weather archive document has no model")
        return f"{dataset}:{model}"

    if dataset == TROPICAL_CYCLONE_TRACK_DATASET:
        storm_id = document.get("storm_id")
        if not isinstance(storm_id, str) or not storm_id:
            raise ValueError("tropical-cyclone archive document has no storm_id")
        return f"{dataset}:{storm_id}"

    return dataset


def infer_archive_policy(document: dict[str, Any]) -> ArchivePolicy:
    if document.get("archive_slot") is not None:
        return ArchivePolicy.SLOT
    return ArchivePolicy.CONTENT


async def build_migration_plan(database: AsyncDatabase) -> ArchiveMigrationPlan:
    archive = database["archive"]
    index_information = await archive.index_information()
    legacy_indexes = tuple(
        name for name in LEGACY_INDEX_NAMES if name in index_information
    )

    projection = {
        "dataset": 1,
        "document_id": 1,
        "archive_policy": 1,
        "archive_slot": 1,
        "model": 1,
        "storm_id": 1,
    }
    payload_identity_datasets = (
        OCF_STATION_FORECAST_DATASET,
        SMART_LAMPPOST_DATASET,
    )
    expected_payload_ids = {}
    payload_cursor = archive.find(
        {"dataset": {"$in": list(payload_identity_datasets)}},
        {"dataset": 1, "payload": 1},
    )
    async for document in payload_cursor:
        expected_payload_ids[document["_id"]] = infer_document_id(document)

    # Scan the small metadata projection for every retained archive record so
    # present-but-invalid values are repaired as well as missing fields.
    cursor = archive.find({}, projection)

    updates = []
    scanned_documents = 0
    document_ids_to_set = 0
    policies_to_set = 0
    async for document in cursor:
        scanned_documents += 1
        fields: dict[str, str] = {}
        existing_document_id = document.get("document_id")
        if document.get("dataset") in payload_identity_datasets:
            expected_document_id = expected_payload_ids.get(document["_id"])
            if expected_document_id is None:
                raise ValueError("archive document disappeared during migration")
        else:
            expected_document_id = infer_document_id(document)
        if existing_document_id != expected_document_id:
            fields["document_id"] = expected_document_id
            document_ids_to_set += 1
        expected_policy = infer_archive_policy(document).value
        if document.get("archive_policy") != expected_policy:
            fields["archive_policy"] = expected_policy
            policies_to_set += 1
        if fields:
            updates.append(UpdateOne({"_id": document["_id"]}, {"$set": fields}))

    return ArchiveMigrationPlan(
        scanned_documents=scanned_documents,
        updates=tuple(updates),
        document_ids_to_set=document_ids_to_set,
        policies_to_set=policies_to_set,
        legacy_indexes=legacy_indexes,
    )


async def apply_migration(
    database: AsyncDatabase,
    plan: ArchiveMigrationPlan,
) -> None:
    archive = database["archive"]
    if plan.updates:
        await archive.bulk_write(list(plan.updates), ordered=True)

    # Create and validate the replacement indexes before removing old ones.
    await ensure_storage_indexes(database)
    for name in plan.legacy_indexes:
        await archive.drop_index(name)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill archive document identity/policy and migrate MongoDB "
            "archive indexes. Dry-run is the default."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the backfill and replace the legacy indexes",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="skip the confirmation prompt (requires --apply)",
    )
    return parser.parse_args()


async def async_main(args: argparse.Namespace) -> int:
    database = get_ingestion_database()
    try:
        plan = await build_migration_plan(database)
        print(f"Database: {database.name}")
        print(f"Archive documents scanned: {plan.scanned_documents}")
        print(f"document_id fields to set: {plan.document_ids_to_set}")
        print(f"archive_policy fields to set: {plan.policies_to_set}")
        print(
            "Legacy indexes to remove: "
            + (", ".join(plan.legacy_indexes) or "none")
        )

        if not args.apply:
            print("Dry run only. Re-run with --apply after reviewing this plan.")
            return 0

        if not args.yes:
            confirmation = input(
                "Apply this archive migration to the database? [y/N] "
            )
            if confirmation.strip().lower() != "y":
                print("No changes applied.")
                return 0

        await apply_migration(database, plan)
        print("Archive identity and index migration completed successfully.")
        return 0
    except (KeyError, TypeError, ValueError, PyMongoError) as error:
        print(f"Archive migration failed: {error}", file=sys.stderr)
        return 1
    finally:
        await close_database_clients()


def main() -> int:
    args = parse_args()
    if args.yes and not args.apply:
        print("--yes requires --apply", file=sys.stderr)
        return 2
    return asyncio.run(async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
