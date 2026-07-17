import asyncio
from unittest.mock import AsyncMock, MagicMock, call

from app.storage import ensure_storage_indexes


def test_storage_indexes_are_created() -> None:
    archive = MagicMock()
    archive.create_index = AsyncMock()
    database = MagicMock()
    database.__getitem__.return_value = archive

    asyncio.run(ensure_storage_indexes(database))

    assert archive.create_index.await_args_list == [
        call(
            [("dataset", 1), ("content_hash", 1)],
            name="archive_dataset_content_unique",
            unique=True,
        ),
        call(
            [("expires_at", 1)],
            name="archive_expiry_ttl",
            expireAfterSeconds=0,
        ),
    ]
