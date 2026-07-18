from typing import Literal

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.server_api import ServerApi

from .config import get_settings

ConnectionRole = Literal["ingestion", "reader"]

_ingestion_client: AsyncMongoClient | None = None
_reader_client: AsyncMongoClient | None = None


def _create_client(uri: str) -> AsyncMongoClient:
    return AsyncMongoClient(
        uri,
        connectTimeoutMS=10_000,
        serverSelectionTimeoutMS=10_000,
        server_api=ServerApi("1", strict=True, deprecation_errors=True),
        tz_aware=True,
    )


def get_client(role: ConnectionRole) -> AsyncMongoClient:
    global _ingestion_client, _reader_client

    settings = get_settings()

    if role == "ingestion":
        if _ingestion_client is None:
            _ingestion_client = _create_client(
                settings.mongodb_ingest_uri.get_secret_value()
            )
        return _ingestion_client

    if _reader_client is None:
        _reader_client = _create_client(settings.mongodb_read_uri.get_secret_value())
    return _reader_client


def get_database(role: ConnectionRole) -> AsyncDatabase:
    settings = get_settings()
    return get_client(role)[settings.mongodb_database]


def get_ingestion_database() -> AsyncDatabase:
    return get_database("ingestion")


def get_read_database() -> AsyncDatabase:
    return get_database("reader")


async def close_database_clients() -> None:
    global _ingestion_client, _reader_client

    clients = (_ingestion_client, _reader_client)
    _ingestion_client = None
    _reader_client = None

    for client in clients:
        if client is not None:
            await client.close()
