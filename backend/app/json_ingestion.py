from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256

import httpx
from pydantic import BaseModel, ValidationError
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError

from .storage import ensure_storage_indexes


@dataclass(frozen=True)
class JsonDatasetSpec[PayloadModel: BaseModel]:
    dataset: str
    document_id: str
    url: str
    payload_model: type[PayloadModel]
    source_updated_at: Callable[[PayloadModel], datetime | None]
    archive_retention: timedelta | None = timedelta(days=3)


@dataclass(frozen=True)
class JsonIngestionResult:
    changed: bool
    source_updated_at: datetime | None
    fetched_at: datetime


class JsonDatasetUpstreamError(Exception):
    def __init__(self, dataset: str) -> None:
        self.dataset = dataset
        super().__init__(dataset)


class JsonDatasetStorageError(Exception):
    def __init__(self, dataset: str) -> None:
        self.dataset = dataset
        super().__init__(dataset)


async def ingest_json_dataset[PayloadModel: BaseModel](
    database: AsyncDatabase,
    client: httpx.AsyncClient,
    spec: JsonDatasetSpec[PayloadModel],
    *,
    now: datetime | None = None,
) -> JsonIngestionResult:
    try:
        response = await client.get(spec.url)
        response.raise_for_status()
        raw_payload = response.content
        validated_payload = spec.payload_model.model_validate_json(raw_payload)
        source_updated_at = spec.source_updated_at(validated_payload)
    except (httpx.HTTPError, ValidationError) as error:
        raise JsonDatasetUpstreamError(spec.dataset) from error

    fetched_at = (now or datetime.now(UTC)).astimezone(UTC)
    content_hash = sha256(raw_payload).hexdigest()
    content_type = response.headers.get("content-type", "application/json")
    content_type = content_type.partition(";")[0].strip() or "application/json"

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
            "source_updated_at": source_updated_at,
            "byte_size": len(raw_payload),
            "content_hash": content_hash,
        }
        await latest.replace_one(
            {"_id": spec.document_id},
            document,
            upsert=True,
        )

        if spec.archive_retention is not None:
            archive_document = {
                key: value for key, value in document.items() if key != "_id"
            }
            archive_document["expires_at"] = (
                fetched_at + spec.archive_retention
            )
            await database["archive"].update_one(
                {
                    "dataset": spec.dataset,
                    "content_hash": content_hash,
                },
                {"$setOnInsert": archive_document},
                upsert=True,
            )
    except PyMongoError as error:
        raise JsonDatasetStorageError(spec.dataset) from error

    return JsonIngestionResult(
        changed=changed,
        source_updated_at=source_updated_at,
        fetched_at=fetched_at,
    )
