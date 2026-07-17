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
