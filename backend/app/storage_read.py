import csv
import io
import json
from collections.abc import Callable
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ValidationError
from pymongo.asynchronous.database import AsyncDatabase


class StoredMetadata(BaseModel):
    source_updated_at: datetime | None = None
    fetched_at: datetime
    content_hash: str | None = None
    content_type: str | None = None
    byte_size: int | None = None


class StoredDocument(StoredMetadata):
    payload: bytes


class DatasetNotFoundError(Exception):
    def __init__(self, dataset: str) -> None:
        self.dataset = dataset
        super().__init__(dataset)


class StoredDataError(Exception):
    def __init__(self, dataset: str) -> None:
        self.dataset = dataset
        super().__init__(dataset)


LATEST_PROJECTION = {
    "_id": 0,
    "payload": 1,
    "source_updated_at": 1,
    "fetched_at": 1,
    "content_hash": 1,
    "content_type": 1,
    "byte_size": 1,
    "bounds": 1,
    "observed_at": 1,
    "raster_width": 1,
    "raster_height": 1,
    "model": 1,
    "model_label": 1,
    "base_time": 1,
    "valid_at": 1,
    "lead_hours": 1,
    "storm_id": 1,
    "storm_name_en": 1,
    "storm_name_zh": 1,
}


async def read_latest_document(
    database: AsyncDatabase,
    document_id: str,
    *,
    projection: dict[str, int] | None = None,
) -> dict[str, Any]:
    document = await database["latest"].find_one(
        {"_id": document_id},
        projection or LATEST_PROJECTION,
    )
    if document is None:
        raise DatasetNotFoundError(document_id)
    return document


def validate_stored_document(
    document: dict[str, Any],
    dataset: str,
) -> StoredDocument:
    try:
        return StoredDocument.model_validate(document)
    except ValidationError as error:
        raise StoredDataError(dataset) from error


def validate_stored_metadata(
    document: dict[str, Any],
    dataset: str,
) -> StoredMetadata:
    try:
        return StoredMetadata.model_validate(document)
    except ValidationError as error:
        raise StoredDataError(dataset) from error


def decode_json_object(
    document: dict[str, Any],
    dataset: str,
    *,
    validate: Callable[[dict[str, Any]], object] | None = None,
) -> tuple[dict[str, Any], StoredDocument]:
    stored = validate_stored_document(document, dataset)
    try:
        payload = json.loads(stored.payload)
        if not isinstance(payload, dict):
            raise ValueError("stored JSON payload must be an object")
        if validate is not None:
            validate(payload)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError, ValueError) as error:
        raise StoredDataError(dataset) from error
    return payload, stored


def decode_csv_rows(
    document: dict[str, Any],
    dataset: str,
    *,
    expected_columns: int,
    normalize_row: Callable[[list[str]], list[str]] | None = None,
) -> tuple[list[list[str]], StoredDocument]:
    stored = validate_stored_document(document, dataset)
    try:
        reader = csv.reader(io.StringIO(stored.payload.decode("utf-8-sig")))
        header = next(reader, None)
        if header is None or len(header) != expected_columns:
            raise ValueError("stored CSV has an unexpected schema")
        rows = []
        for row in reader:
            if not row:
                continue
            if normalize_row is not None:
                row = normalize_row(row)
            if len(row) != expected_columns:
                raise ValueError("stored CSV row has an unexpected schema")
            rows.append(row)
        if not rows:
            raise ValueError("stored CSV is empty")
    except (csv.Error, UnicodeDecodeError, ValueError) as error:
        raise StoredDataError(dataset) from error
    return rows, stored


def read_binary_payload(
    document: dict[str, Any],
    dataset: str,
    *,
    expected_content_type: str,
    signature: bytes | None = None,
) -> tuple[bytes, StoredDocument]:
    stored = validate_stored_document(document, dataset)
    if stored.content_type not in {None, expected_content_type}:
        raise StoredDataError(dataset)
    payload = bytes(stored.payload)
    if signature is not None and not payload.startswith(signature):
        raise StoredDataError(dataset)
    if not payload:
        raise StoredDataError(dataset)
    return payload, stored
