import asyncio
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from pymongo.errors import OperationFailure

from app.storage import ensure_storage_indexes


def test_storage_indexes_are_created() -> None:
    archive = MagicMock()
    archive.create_index = AsyncMock()
    database = MagicMock()
    database.__getitem__.return_value = archive

    asyncio.run(ensure_storage_indexes(database))

    assert archive.create_index.await_args_list == [
        call(
            [("dataset", 1), ("document_id", 1), ("content_hash", 1)],
            name="archive_content_identity_unique",
            unique=True,
            partialFilterExpression={"archive_policy": "content"},
        ),
        call(
            [("expires_at", 1)],
            name="archive_expiry_ttl",
            expireAfterSeconds=0,
        ),
        call(
            [("dataset", 1), ("document_id", 1), ("archive_slot", 1)],
            name="archive_slot_identity_unique",
            unique=True,
            partialFilterExpression={"archive_policy": "slot"},
        ),
        call(
            [("dataset", 1), ("document_id", 1), ("source_updated_at", 1)],
            name="archive_dataset_document_source_updated",
        ),
        call(
            [("dataset", 1), ("document_id", 1), ("observed_at", 1)],
            name="archive_dataset_document_observed",
        ),
        call(
            [("dataset", 1), ("document_id", 1), ("valid_at", 1)],
            name="archive_dataset_document_valid",
        ),
    ]


def test_storage_indexes_are_initialized_once_for_concurrent_writers() -> None:
    archive = MagicMock()
    archive.create_index = AsyncMock()
    database = MagicMock()
    database.__getitem__.return_value = archive

    async def initialize_concurrently() -> None:
        await asyncio.gather(
            ensure_storage_indexes(database),
            ensure_storage_indexes(database),
            ensure_storage_indexes(database),
        )
        await ensure_storage_indexes(database)

    asyncio.run(initialize_concurrently())

    assert archive.create_index.await_count == 6


def test_failed_storage_index_initialization_can_retry() -> None:
    archive = MagicMock()
    archive.create_index = AsyncMock(
        side_effect=[OperationFailure("index failed"), *([None] * 6)]
    )
    database = MagicMock()
    database.__getitem__.return_value = archive

    async def fail_then_retry() -> None:
        with pytest.raises(OperationFailure):
            await ensure_storage_indexes(database)
        await ensure_storage_indexes(database)

    asyncio.run(fail_then_retry())

    assert archive.create_index.await_count == 7
