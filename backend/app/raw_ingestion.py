from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx
from pymongo.asynchronous.database import AsyncDatabase

from .ingestion import (
    DatasetIngestionResult,
    IngestionTarget,
    ValidatedPayload,
    ingest_dataset,
)
from .storage import ArchivePolicy

ValidatedRawPayload = ValidatedPayload


@dataclass(frozen=True)
class RawDatasetSpec:
    dataset: str
    document_id: str
    url: str
    validate: Callable[[bytes], ValidatedRawPayload]
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


RawIngestionResult = DatasetIngestionResult


async def ingest_raw_dataset(
    database: AsyncDatabase,
    client: httpx.AsyncClient,
    spec: RawDatasetSpec,
    *,
    now: datetime | None = None,
    prefetched_response: httpx.Response | None = None,
) -> RawIngestionResult:
    return await ingest_dataset(
        database,
        client,
        IngestionTarget(
            dataset=spec.dataset,
            document_id=spec.document_id,
            url=spec.url,
            default_content_type=spec.default_content_type,
            archive_retention=spec.archive_retention,
            archive_policy=spec.archive_policy,
            archive_interval=spec.archive_interval,
        ),
        spec.validate,
        now=now,
        prefetched_response=prefetched_response,
    )
