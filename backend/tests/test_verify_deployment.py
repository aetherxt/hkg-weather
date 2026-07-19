import json
from pathlib import Path

import httpx
import pytest

from scripts.verify_deployment import (
    DeploymentVerifier,
    VerificationError,
    load_cron_secret,
    normalize_deployment_url,
)

DEPLOYMENT_URL = "https://weather.example"
INGESTED_FETCHED_AT = "2026-07-18T10:00:00.430834Z"
STORED_FETCHED_AT = "2026-07-18T10:00:00.430000Z"
PNG = b"\x89PNG\r\n\x1a\nradar"


def verifier_for(handler: httpx.MockTransport) -> DeploymentVerifier:
    return DeploymentVerifier(
        DEPLOYMENT_URL,
        client=httpx.Client(transport=handler),
    )


def json_response(payload: object, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code,
        headers={"Content-Type": "application/json"},
        content=json.dumps(payload).encode(),
    )


def test_normalize_deployment_url_requires_https_except_locally() -> None:
    assert normalize_deployment_url("https://weather.example/") == DEPLOYMENT_URL
    assert normalize_deployment_url("http://localhost:3000/") == (
        "http://localhost:3000"
    )
    with pytest.raises(ValueError, match="requires HTTPS"):
        normalize_deployment_url("http://weather.example")


def test_load_cron_secret_reads_web_env_file(tmp_path: Path) -> None:
    web = tmp_path / "web"
    web.mkdir()
    (web / ".env.local").write_text(
        'OTHER="value"\nCRON_SECRET="secret/value+1="\n',
        encoding="utf-8",
    )

    assert load_cron_secret(tmp_path) == "secret/value+1="


def test_ingest_all_accepts_unchanged_data_and_extracts_current_timestamp() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer secret"
        return json_response(
            {
                "ok": True,
                "jobs": [
                    {
                        "job": "current_weather",
                        "ok": True,
                        "datasets": [
                            {
                                "dataset": "current_weather",
                                "changed": False,
                                "sourceUpdatedAt": "2026-07-18T09:55:00Z",
                                "fetchedAt": INGESTED_FETCHED_AT,
                            }
                        ],
                        "detail": None,
                    },
                    {
                        "job": "tropical_cyclones",
                        "ok": True,
                        "datasets": [],
                        "detail": None,
                    },
                ],
            }
        )

    verifier = verifier_for(httpx.MockTransport(handler))

    detail, fetched_at = verifier.ingest_all("secret")

    assert detail == "2 jobs passed and reported 1 datasets"
    assert fetched_at == INGESTED_FETCHED_AT


def test_ingest_all_reports_failed_job() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return json_response(
            {
                "ok": False,
                "jobs": [
                    {
                        "job": "radar_128",
                        "ok": False,
                        "datasets": [],
                        "detail": "upstream weather data unavailable",
                    }
                ],
            },
            status_code=502,
        )

    verifier = verifier_for(httpx.MockTransport(handler))

    with pytest.raises(VerificationError, match="radar_128.*upstream"):
        verifier.ingest_all("secret")


def test_ingest_all_reports_authentication_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return json_response({"detail": "Unauthorized"}, status_code=401)

    verifier = verifier_for(httpx.MockTransport(handler))

    with pytest.raises(VerificationError, match="HTTP 401: Unauthorized"):
        verifier.ingest_all("wrong-secret")


def test_current_weather_must_match_ingested_timestamp() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return json_response(
            {
                "data": {"updateTime": "2026-07-18T17:55:00+08:00"},
                "meta": {
                    "dataset": "current_weather",
                    "sourceUpdatedAt": "2026-07-18T09:55:00Z",
                    "fetchedAt": STORED_FETCHED_AT,
                },
            }
        )

    verifier = verifier_for(httpx.MockTransport(handler))

    assert STORED_FETCHED_AT in verifier.verify_current_weather(INGESTED_FETCHED_AT)
    with pytest.raises(VerificationError, match="just-ingested"):
        verifier.verify_current_weather("2026-07-18T10:01:00Z")


def test_nowcast_verifies_grid_dimensions() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/weather/rainfall/nowcast":
            return json_response(
                {
                    "data": [
                        {
                            "validAt": "2026-07-18T18:30:00+08:00",
                            "url": "/api/weather/rainfall/nowcast/202607181830",
                        }
                    ],
                    "meta": {"count": 1},
                }
            )
        return json_response(
            {
                "data": {
                    "width": 2,
                    "height": 2,
                    "values": [0.0, 0.1, 0.2, 0.3],
                },
                "meta": {"dataset": "gridded_rainfall_nowcast"},
            }
        )

    verifier = verifier_for(httpx.MockTransport(handler))

    assert verifier.verify_nowcast() == "decoded 1 frames; first grid is 2x2"


def test_radar_verifies_png_headers_and_etag() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/weather/radar":
            return json_response(
                {
                    "data": {
                        "width": 480,
                        "height": 480,
                        "imageUrl": "/api/weather/radar/image",
                    },
                    "meta": {"dataset": "radar_128"},
                }
            )
        if request.headers.get("If-None-Match") == '"radar-hash"':
            return httpx.Response(304, headers={"ETag": '"radar-hash"'})
        return httpx.Response(
            200,
            headers={
                "Content-Type": "image/png",
                "Content-Length": str(len(PNG)),
                "ETag": '"radar-hash"',
            },
            content=PNG,
        )

    verifier = verifier_for(httpx.MockTransport(handler))

    detail = verifier.verify_radar()

    assert "PNG" in detail
    assert "ETag" in detail
