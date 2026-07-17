from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import httpx
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError

from .json_ingestion import (
    JsonDatasetStorageError,
    JsonDatasetUpstreamError,
)
from .storage import ensure_storage_indexes


@dataclass(frozen=True)
class ValidatedRawPayload:
    source_updated_at: datetime | None
    archive_payload: bytes | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class RawDatasetSpec:
    dataset: str
    document_id: str
    url: str
    validate: Callable[[bytes], ValidatedRawPayload]
    default_content_type: str
    archive_retention: timedelta | None = timedelta(days=3)
    archive_interval: timedelta | None = None


@dataclass(frozen=True)
class RawIngestionResult:
    changed: bool
    source_updated_at: datetime | None
    fetched_at: datetime


def _archive_slot(fetched_at: datetime, interval: timedelta) -> datetime:
    interval_seconds = int(interval.total_seconds())
    if interval_seconds <= 0:
        raise ValueError("archive interval must be positive")
    timestamp = int(fetched_at.timestamp())
    return datetime.fromtimestamp(
        timestamp - (timestamp % interval_seconds),
        tz=UTC,
    )


async def ingest_raw_dataset(
    database: AsyncDatabase,
    client: httpx.AsyncClient,
    spec: RawDatasetSpec,
    *,
    now: datetime | None = None,
) -> RawIngestionResult:
    try:
        response = await client.get(spec.url)
        response.raise_for_status()
        raw_payload = response.content
        validated = spec.validate(raw_payload)
    except (httpx.HTTPError, UnicodeError, ValueError) as error:
        raise JsonDatasetUpstreamError(spec.dataset) from error

    fetched_at = (now or datetime.now(UTC)).astimezone(UTC)
    content_hash = sha256(raw_payload).hexdigest()
    content_type = response.headers.get(
        "content-type",
        spec.default_content_type,
    )
    content_type = content_type.partition(";")[0].strip() or spec.default_content_type

    try:
        await ensure_storage_indexes(database)

        latest = database["latest"]
        previous = await latest.find_one(
            {"_id": spec.document_id},
            {"content_hash": 1},
        )
        changed = previous is None or previous.get("content_hash") != content_hash

        document = {
            "_id": spec.document_id,
            "dataset": spec.dataset,
            "source_url": spec.url,
            "content_type": content_type,
            "payload": raw_payload,
            "fetched_at": fetched_at,
            "source_updated_at": validated.source_updated_at,
            "byte_size": len(raw_payload),
            "content_hash": content_hash,
        }
        document.update(validated.metadata)
        await latest.replace_one(
            {"_id": spec.document_id},
            document,
            upsert=True,
        )

        if spec.archive_retention is not None:
            archive_payload = validated.archive_payload or raw_payload
            archive_hash = sha256(archive_payload).hexdigest()
            archive_document = {
                key: value for key, value in document.items() if key != "_id"
            }
            archive_document.update(
                {
                    "payload": archive_payload,
                    "byte_size": len(archive_payload),
                    "content_hash": archive_hash,
                    "expires_at": fetched_at + spec.archive_retention,
                }
            )
            archive_filter: dict[str, object]
            if spec.archive_interval is None:
                archive_filter = {
                    "dataset": spec.dataset,
                    "content_hash": archive_hash,
                }
            else:
                slot = _archive_slot(fetched_at, spec.archive_interval)
                archive_document["archive_slot"] = slot
                archive_filter = {
                    "dataset": spec.dataset,
                    "archive_slot": slot,
                }

            await database["archive"].update_one(
                archive_filter,
                {"$setOnInsert": archive_document},
                upsert=True,
            )
    except PyMongoError as error:
        raise JsonDatasetStorageError(spec.dataset) from error

    return RawIngestionResult(
        changed=changed,
        source_updated_at=validated.source_updated_at,
        fetched_at=fetched_at,
    )
