import asyncio
from collections.abc import Awaitable, Callable

import httpx
import pytest

from app.ingestion import DatasetUpstreamError
from app.rainfall_nowcast import fetch_gridded_rainfall_csv

URL = "https://example.test/nowcast.csv"
DATASET = "gridded_rainfall_nowcast"
ETAG = '"nowcast-v1"'

Handler = Callable[[httpx.Request], httpx.Response | Awaitable[httpx.Response]]


def fetch(
    handler: Handler,
    *,
    known_etag: str | None = None,
    timeout_seconds: float = 1,
):
    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
        ) as client:
            return await fetch_gridded_rainfall_csv(
                client,
                URL,
                DATASET,
                known_etag=known_etag,
                timeout_seconds=timeout_seconds,
            )

    return asyncio.run(run())


def partial_response(
    request: httpx.Request,
    payload: bytes,
    start: int,
    end: int,
    *,
    etag: str = ETAG,
) -> httpx.Response:
    return httpx.Response(
        206,
        content=payload[start : end + 1],
        headers=[
            ("Content-Range", f"bytes {start}-{end}/{len(payload)}"),
            ("Content-Type", "application/octet-stream"),
            ("Content-Type", "text/csv; charset=utf-8"),
            ("ETag", etag),
        ],
        request=request,
    )


def requested_range(request: httpx.Request) -> tuple[int, int]:
    value = request.headers["Range"].removeprefix("bytes=")
    start, separator, end = value.partition("-")
    assert separator
    return int(start), int(end)


def test_matching_etag_skips_nowcast_download() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Range"] == "bytes=0-0"
        assert request.headers["If-None-Match"] == ETAG
        return httpx.Response(304, request=request)

    assert fetch(handler, known_etag=ETAG) is None


def test_changed_nowcast_downloads_and_reassembles_four_ranges() -> None:
    payload = b"abcdefghij"
    requested: list[tuple[int, int]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        start, end = requested_range(request)
        if (start, end) == (0, 0) and "If-Match" not in request.headers:
            return partial_response(request, payload, 0, 0)
        assert request.headers["If-Match"] == ETAG
        requested.append((start, end))
        return partial_response(request, payload, start, end)

    result = fetch(handler)

    assert result is not None
    assert result.payload == payload
    assert result.etag == ETAG
    assert result.content_type == "text/csv"
    assert requested == [(0, 2), (3, 5), (6, 8), (9, 9)]


def test_nowcast_rejects_chunks_from_different_versions() -> None:
    payload = b"abcdefgh"

    def handler(request: httpx.Request) -> httpx.Response:
        start, end = requested_range(request)
        if (start, end) == (0, 0) and "If-Match" not in request.headers:
            return partial_response(request, payload, 0, 0)
        etag = '"nowcast-v2"' if start == 2 else ETAG
        return partial_response(request, payload, start, end, etag=etag)

    with pytest.raises(DatasetUpstreamError) as error:
        fetch(handler)

    assert isinstance(error.value.__cause__, ValueError)


def test_nowcast_download_has_an_overall_timeout() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.05)
        return partial_response(request, b"abcdefgh", 0, 0)

    with pytest.raises(DatasetUpstreamError) as error:
        fetch(handler, timeout_seconds=0.001)

    assert isinstance(error.value.__cause__, TimeoutError)
