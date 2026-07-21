from collections.abc import AsyncIterator

import httpx

UPSTREAM_TIMEOUT = httpx.Timeout(30.0, connect=10.0)


async def get_http_client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        timeout=UPSTREAM_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": "hkg-weather/0.1"},
    ) as client:
        yield client
