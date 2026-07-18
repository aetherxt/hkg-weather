from pymongo import ASCENDING
from pymongo.asynchronous.database import AsyncDatabase


async def ensure_storage_indexes(database: AsyncDatabase) -> None:
    archive = database["archive"]

    await archive.create_index(
        [("dataset", ASCENDING), ("content_hash", ASCENDING)],
        name="archive_dataset_content_unique",
        unique=True,
    )
    await archive.create_index(
        [("expires_at", ASCENDING)],
        name="archive_expiry_ttl",
        expireAfterSeconds=0,
    )
    await archive.create_index(
        [("dataset", ASCENDING), ("archive_slot", ASCENDING)],
        name="archive_dataset_slot_unique",
        unique=True,
        partialFilterExpression={"archive_slot": {"$exists": True}},
    )
    await archive.create_index(
        [("dataset", ASCENDING), ("source_updated_at", ASCENDING)],
        name="archive_dataset_source_updated",
    )
    await archive.create_index(
        [("dataset", ASCENDING), ("observed_at", ASCENDING)],
        name="archive_dataset_observed",
    )
    await archive.create_index(
        [("dataset", ASCENDING), ("model", ASCENDING), ("valid_at", ASCENDING)],
        name="archive_dataset_model_valid",
    )
