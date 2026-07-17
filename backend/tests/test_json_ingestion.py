import asyncio
import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import httpx
from pydantic import BaseModel, Field

from app.json_ingestion import JsonDatasetSpec, ingest_json_dataset

DUMMY_URL = "https://example.test/dataset.json"


class DummyPayload(BaseModel):
    generated_at: datetime = Field(alias="generatedAt")


def test_json_ingestion_uses_dataset_specification() -> None:
    payload = {"generatedAt": "2026-07-17T18:00:00+08:00", "value": 7}
    response = httpx.Response(
        200,
        content=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
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

    retention = timedelta(hours=12)
    fetched_at = datetime(2026, 7, 17, 10, 1, tzinfo=UTC)
    spec = JsonDatasetSpec(
        dataset="dummy_dataset",
        document_id="dummy_latest",
        url=DUMMY_URL,
        payload_model=DummyPayload,
        source_updated_at=lambda value: value.generated_at,
        archive_retention=retention,
    )

    result = asyncio.run(
        ingest_json_dataset(database, client, spec, now=fetched_at)
    )

    assert result.changed is True
    assert result.source_updated_at == datetime.fromisoformat(
        "2026-07-17T18:00:00+08:00"
    )
    latest_document = latest.replace_one.await_args.args[1]
    assert latest_document["_id"] == "dummy_latest"
    assert latest_document["dataset"] == "dummy_dataset"
    assert latest_document["source_url"] == DUMMY_URL
    archive_document = archive.update_one.await_args.args[1]["$setOnInsert"]
    assert archive_document["expires_at"] == fetched_at + retention
