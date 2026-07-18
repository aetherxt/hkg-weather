import asyncio
from enum import StrEnum

from pymongo import ASCENDING
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.asynchronous.mongo_client import AsyncMongoClient


class ArchivePolicy(StrEnum):
    CONTENT = "content"
    SLOT = "slot"


type DatabaseIdentity = tuple[AsyncMongoClient, str]

_initialized_databases: set[DatabaseIdentity] = set()
_index_initialization_tasks: dict[DatabaseIdentity, asyncio.Task[None]] = {}


def _database_identity(database: AsyncDatabase) -> DatabaseIdentity:
    return database.client, database.name


async def _create_storage_indexes(database: AsyncDatabase) -> None:
    archive = database["archive"]

    await archive.create_index(
        [
            ("dataset", ASCENDING),
            ("document_id", ASCENDING),
            ("content_hash", ASCENDING),
        ],
        name="archive_content_identity_unique",
        unique=True,
        partialFilterExpression={"archive_policy": ArchivePolicy.CONTENT.value},
    )
    await archive.create_index(
        [("expires_at", ASCENDING)],
        name="archive_expiry_ttl",
        expireAfterSeconds=0,
    )
    await archive.create_index(
        [
            ("dataset", ASCENDING),
            ("document_id", ASCENDING),
            ("archive_slot", ASCENDING),
        ],
        name="archive_slot_identity_unique",
        unique=True,
        partialFilterExpression={"archive_policy": ArchivePolicy.SLOT.value},
    )
    await archive.create_index(
        [
            ("dataset", ASCENDING),
            ("document_id", ASCENDING),
            ("source_updated_at", ASCENDING),
        ],
        name="archive_dataset_document_source_updated",
    )
    await archive.create_index(
        [
            ("dataset", ASCENDING),
            ("document_id", ASCENDING),
            ("observed_at", ASCENDING),
        ],
        name="archive_dataset_document_observed",
    )
    await archive.create_index(
        [
            ("dataset", ASCENDING),
            ("document_id", ASCENDING),
            ("valid_at", ASCENDING),
        ],
        name="archive_dataset_document_valid",
    )


async def ensure_storage_indexes(database: AsyncDatabase) -> None:
    """Create storage indexes once per MongoDB client/database in this process."""
    identity = _database_identity(database)
    if identity in _initialized_databases:
        return

    task = _index_initialization_tasks.get(identity)
    if task is None:
        task = asyncio.create_task(_create_storage_indexes(database))
        _index_initialization_tasks[identity] = task

    try:
        await asyncio.shield(task)
    except BaseException:
        if task.done() and _index_initialization_tasks.get(identity) is task:
            _index_initialization_tasks.pop(identity, None)
        raise
    else:
        _initialized_databases.add(identity)
        if _index_initialization_tasks.get(identity) is task:
            _index_initialization_tasks.pop(identity, None)
