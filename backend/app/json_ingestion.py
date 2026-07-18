from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx
from pydantic import BaseModel
from pymongo.asynchronous.database import AsyncDatabase

from .ingestion import (
    DatasetIngestionResult,
    DatasetStorageError,
    DatasetUpstreamError,
    IngestionTarget,
    ValidatedPayload,
    ingest_dataset,
)


@dataclass(frozen=True)
class JsonDatasetSpec[PayloadModel: BaseModel]:
    dataset: str
    document_id: str
    url: str
    payload_model: type[PayloadModel]
    source_updated_at: Callable[[PayloadModel], datetime | None]
    archive_retention: timedelta | None = timedelta(days=3)


JsonIngestionResult = DatasetIngestionResult
JsonDatasetUpstreamError = DatasetUpstreamError
JsonDatasetStorageError = DatasetStorageError


async def ingest_json_dataset[PayloadModel: BaseModel](
    database: AsyncDatabase,
    client: httpx.AsyncClient,
    spec: JsonDatasetSpec[PayloadModel],
    *,
    now: datetime | None = None,
) -> JsonIngestionResult:
    def validate(raw_payload: bytes) -> ValidatedPayload:
        payload = spec.payload_model.model_validate_json(raw_payload)
        return ValidatedPayload(source_updated_at=spec.source_updated_at(payload))

    return await ingest_dataset(
        database,
        client,
        IngestionTarget(
            dataset=spec.dataset,
            document_id=spec.document_id,
            url=spec.url,
            default_content_type="application/json",
            archive_retention=spec.archive_retention,
        ),
        validate,
        now=now,
    )
