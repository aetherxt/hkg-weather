import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.raw_ingestion import (
    RawDatasetSpec,
    ValidatedRawPayload,
    ingest_raw_dataset,
)
from app.storage import ArchivePolicy

DUMMY_URL = "https://example.test/weather.csv"


def test_raw_ingestion_stores_latest_and_interval_archive() -> None:
    raw_payload = b"time,value\n202607171800,1\n"
    archive_payload = b"time,value\n202607171800,1\n"
    response = httpx.Response(
        200,
        content=raw_payload,
        headers={"Content-Type": "text/csv; charset=utf-8"},
        request=httpx.Request("GET", DUMMY_URL),
    )
    client = MagicMock()
    client.get = AsyncMock(return_value=response)

    latest = MagicMock()
    latest.find_one = AsyncMock(return_value=None)
    latest.replace_one = AsyncMock()
    archive = MagicMock()
    archive.create_index = AsyncMock()
    archive.update_one = AsyncMock()
    database = MagicMock()
    database.__getitem__.side_effect = {
        "latest": latest,
        "archive": archive,
    }.__getitem__

    source_updated_at = datetime(2026, 7, 17, 10, tzinfo=UTC)
    fetched_at = datetime(2026, 7, 17, 10, 38, tzinfo=UTC)
    spec = RawDatasetSpec(
        dataset="dummy_csv",
        document_id="dummy_csv",
        url=DUMMY_URL,
        validate=lambda _: ValidatedRawPayload(
            source_updated_at=source_updated_at,
            archive_payload=archive_payload,
            metadata={"valid_at": source_updated_at, "lead_minutes": 30},
        ),
        default_content_type="text/csv",
        archive_retention=timedelta(days=3),
        archive_policy=ArchivePolicy.SLOT,
        archive_interval=timedelta(minutes=30),
    )

    result = asyncio.run(ingest_raw_dataset(database, client, spec, now=fetched_at))

    assert result.changed is True
    latest_document = latest.replace_one.await_args.args[1]
    assert latest_document["payload"] == raw_payload
    assert latest_document["content_type"] == "text/csv"
    assert latest_document["valid_at"] == source_updated_at
    assert latest_document["lead_minutes"] == 30

    archive_filter = archive.update_one.await_args.args[0]
    archive_document = archive.update_one.await_args.args[1]["$setOnInsert"]
    assert archive_filter == {
        "dataset": "dummy_csv",
        "document_id": "dummy_csv",
        "archive_policy": "slot",
        "archive_slot": datetime(2026, 7, 17, 10, 30, tzinfo=UTC),
    }
    assert archive_document["document_id"] == "dummy_csv"
    assert archive_document["archive_policy"] == "slot"
    assert archive_document["payload"] == archive_payload
    assert archive_document["valid_at"] == source_updated_at
    assert archive_document["archive_slot"] == datetime(
        2026, 7, 17, 10, 30, tzinfo=UTC
    )


def test_raw_archive_policy_requires_a_consistent_interval() -> None:
    with pytest.raises(ValueError, match="require an interval"):
        RawDatasetSpec(
            dataset="dummy",
            document_id="dummy",
            url=DUMMY_URL,
            validate=lambda _: ValidatedRawPayload(source_updated_at=None),
            default_content_type="text/csv",
            archive_policy=ArchivePolicy.SLOT,
        )

    with pytest.raises(ValueError, match="cannot define an interval"):
        RawDatasetSpec(
            dataset="dummy",
            document_id="dummy",
            url=DUMMY_URL,
            validate=lambda _: ValidatedRawPayload(source_updated_at=None),
            default_content_type="text/csv",
            archive_interval=timedelta(minutes=30),
        )
