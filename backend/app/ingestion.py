from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import httpx
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError

from .storage import ArchivePolicy, ensure_storage_indexes


@dataclass(frozen=True)
class ValidatedPayload:
    source_updated_at: datetime | None
    archive_payload: bytes | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class IngestionTarget:
    dataset: str
    document_id: str
    url: str
    default_content_type: str
    archive_retention: timedelta | None = timedelta(days=3)
    archive_policy: ArchivePolicy = ArchivePolicy.CONTENT
    archive_interval: timedelta | None = None

    def __post_init__(self) -> None:
        if self.archive_policy is ArchivePolicy.SLOT:
            if self.archive_interval is None:
                raise ValueError("slot-addressed archives require an interval")
            if self.archive_interval.total_seconds() <= 0:
                raise ValueError("archive interval must be positive")
        elif self.archive_interval is not None:
            raise ValueError("content-addressed archives cannot define an interval")


@dataclass(frozen=True)
class DatasetIngestionResult:
    changed: bool
    source_updated_at: datetime | None
    fetched_at: datetime


class DatasetUpstreamError(Exception):
    def __init__(self, dataset: str) -> None:
        self.dataset = dataset
        super().__init__(dataset)


class DatasetStorageError(Exception):
    def __init__(self, dataset: str) -> None:
        self.dataset = dataset
        super().__init__(dataset)


def _archive_slot(fetched_at: datetime, interval: timedelta) -> datetime:
    interval_seconds = int(interval.total_seconds())
    timestamp = int(fetched_at.timestamp())
    return datetime.fromtimestamp(
        timestamp - (timestamp % interval_seconds),
        tz=UTC,
    )


async def ingest_dataset(
    database: AsyncDatabase,
    client: httpx.AsyncClient,
    target: IngestionTarget,
    validate: Callable[[bytes], ValidatedPayload],
    *,
    now: datetime | None = None,
) -> DatasetIngestionResult:
    try:
        response = await client.get(target.url)
        response.raise_for_status()
        raw_payload = response.content
        validated = validate(raw_payload)
    except (httpx.HTTPError, UnicodeError, ValueError) as error:
        raise DatasetUpstreamError(target.dataset) from error

    fetched_at = (now or datetime.now(UTC)).astimezone(UTC)
    content_hash = sha256(raw_payload).hexdigest()
    content_type = response.headers.get(
        "content-type",
        target.default_content_type,
    )
    content_type = content_type.partition(";")[0].strip() or target.default_content_type

    document = {
        "_id": target.document_id,
        "dataset": target.dataset,
        "source_url": target.url,
        "content_type": content_type,
        "payload": raw_payload,
        "fetched_at": fetched_at,
        "source_updated_at": validated.source_updated_at,
        "byte_size": len(raw_payload),
        "content_hash": content_hash,
    }
    document.update(validated.metadata)

    archive_filter: dict[str, object] | None = None
    archive_document: dict[str, object] | None = None
    if target.archive_retention is not None:
        archive_payload = (
            raw_payload
            if validated.archive_payload is None
            else validated.archive_payload
        )
        archive_hash = sha256(archive_payload).hexdigest()
        archive_document = {
            key: value for key, value in document.items() if key != "_id"
        }
        archive_document.update(
            {
                "document_id": target.document_id,
                "archive_policy": target.archive_policy.value,
                "payload": archive_payload,
                "byte_size": len(archive_payload),
                "content_hash": archive_hash,
                "expires_at": fetched_at + target.archive_retention,
            }
        )
        if target.archive_policy is ArchivePolicy.CONTENT:
            archive_filter = {
                "dataset": target.dataset,
                "document_id": target.document_id,
                "archive_policy": ArchivePolicy.CONTENT.value,
                "content_hash": archive_hash,
            }
        else:
            # IngestionTarget validates this invariant at construction.
            assert target.archive_interval is not None
            slot = _archive_slot(fetched_at, target.archive_interval)
            archive_document["archive_slot"] = slot
            archive_filter = {
                "dataset": target.dataset,
                "document_id": target.document_id,
                "archive_policy": ArchivePolicy.SLOT.value,
                "archive_slot": slot,
            }

    try:
        await ensure_storage_indexes(database)
        latest = database["latest"]
        previous = await latest.find_one(
            {"_id": target.document_id},
            {"content_hash": 1},
        )
        changed = previous is None or previous.get("content_hash") != content_hash
        await latest.replace_one(
            {"_id": target.document_id},
            document,
            upsert=True,
        )
        if archive_filter is not None and archive_document is not None:
            await database["archive"].update_one(
                archive_filter,
                {"$setOnInsert": archive_document},
                upsert=True,
            )
    except PyMongoError as error:
        raise DatasetStorageError(target.dataset) from error

    return DatasetIngestionResult(
        changed=changed,
        source_updated_at=validated.source_updated_at,
        fetched_at=fetched_at,
    )
