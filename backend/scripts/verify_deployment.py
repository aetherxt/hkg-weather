from __future__ import annotations

import argparse
import ast
import sys
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit
from uuid import uuid4

import httpx

DEPLOYMENT_URL = "https://hkgweather.vercel.app"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class VerificationError(RuntimeError):
    pass


def read_env_value(path: Path, name: str) -> str | None:
    if not path.is_file():
        return None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, raw_value = line.partition("=")
        if not separator or key.strip() != name:
            continue
        value = raw_value.strip()
        if value[:1] in {'"', "'"}:
            try:
                parsed = ast.literal_eval(value)
            except (SyntaxError, ValueError) as error:
                raise ValueError(f"invalid {name} value in {path}") from error
            if not isinstance(parsed, str):
                raise ValueError(f"invalid {name} value in {path}")
            value = parsed
        return value or None
    return None


def load_cron_secret(repository_root: Path = REPOSITORY_ROOT) -> str:
    env_paths = (
        repository_root / ".env.local",
        repository_root / "web" / ".env.local",
    )
    for path in env_paths:
        value = read_env_value(path, "CRON_SECRET")
        if value:
            return value
    checked = ", ".join(str(path) for path in env_paths)
    raise ValueError(f"CRON_SECRET was not found in {checked}")


def normalize_deployment_url(value: str) -> str:
    url = value.strip().rstrip("/")
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("deployment URL must be an absolute HTTP(S) URL")
    if parsed.query or parsed.fragment:
        raise ValueError("deployment URL cannot contain a query or fragment")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise ValueError("deployed verification requires HTTPS")
    return url


def api_timestamp(value: str, label: str) -> datetime:
    normalized = f"{value[:-1]}+00:00" if value.endswith("Z") else value
    try:
        timestamp = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise VerificationError(f"{label} is not a valid ISO-8601 timestamp") from error
    if timestamp.tzinfo is None:
        raise VerificationError(f"{label} does not include a timezone")
    return timestamp


def matches_mongodb_timestamp(expected: str, actual: str) -> bool:
    expected_time = api_timestamp(expected, "ingestion fetchedAt")
    actual_time = api_timestamp(actual, "reader meta.fetchedAt")
    expected_milliseconds = expected_time.replace(
        microsecond=(expected_time.microsecond // 1000) * 1000
    )
    return actual_time == expected_milliseconds


def response_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        text = response.text.strip().replace("\n", " ")
        return text[:300] or "empty response"
    if isinstance(payload, dict):
        detail = payload.get("detail")
        if isinstance(detail, str):
            return detail[:300]
    return "unexpected response"


def json_object(response: httpx.Response, label: str) -> dict[str, Any]:
    if response.status_code != 200:
        raise VerificationError(
            f"{label} returned HTTP {response.status_code}: {response_detail(response)}"
        )
    try:
        payload = response.json()
    except ValueError as error:
        raise VerificationError(f"{label} did not return JSON") from error
    if not isinstance(payload, dict):
        raise VerificationError(f"{label} returned an invalid JSON document")
    return payload


def required_object(
    value: object,
    field: str,
    label: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise VerificationError(f"{label} has an invalid {field} field")
    return value


def required_list(value: object, field: str, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise VerificationError(f"{label} has an invalid {field} field")
    return value


class DeploymentVerifier:
    def __init__(
        self,
        deployment_url: str,
        *,
        timeout: float = 30,
        ingestion_timeout: float = 300,
        client: httpx.Client | None = None,
    ) -> None:
        self.deployment_url = normalize_deployment_url(deployment_url)
        self.ingestion_timeout = ingestion_timeout
        self._owns_client = client is None
        self.client = client or httpx.Client(
            follow_redirects=True,
            timeout=httpx.Timeout(timeout, connect=min(timeout, 30)),
            headers={"User-Agent": "hkg-weather-deployment-verifier/1.0"},
        )

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def endpoint(self, path: str) -> str:
        target = urljoin(f"{self.deployment_url}/", path.lstrip("/"))
        expected = urlsplit(self.deployment_url)
        actual = urlsplit(target)
        if (actual.scheme, actual.netloc) != (expected.scheme, expected.netloc):
            raise VerificationError("API returned a URL on a different origin")
        return target

    def verify_health(self) -> str:
        response = self.client.get(self.endpoint("/api/health"))
        payload = json_object(response, "application health")
        if payload.get("ok") is not True:
            raise VerificationError("application health did not report ok=true")
        return "application reported ok=true"

    def ingest_all(self, cron_secret: str) -> tuple[str, str | None]:
        response = self.client.post(
            self.endpoint("/api/cron/ingest-all"),
            headers={"Authorization": f"Bearer {cron_secret}"},
            timeout=self.ingestion_timeout,
        )
        try:
            payload = response.json()
        except ValueError as error:
            raise VerificationError(
                "ingest-all returned "
                f"HTTP {response.status_code} with a non-JSON response"
            ) from error
        if not isinstance(payload, dict):
            raise VerificationError("ingest-all returned an invalid JSON document")

        raw_jobs = payload.get("jobs")
        if response.status_code != 200 and not isinstance(raw_jobs, list):
            raise VerificationError(
                f"ingest-all returned HTTP {response.status_code}: "
                f"{response_detail(response)}"
            )
        jobs = required_list(raw_jobs, "jobs", "ingest-all")
        failed_jobs = []
        dataset_count = 0
        current_fetched_at: str | None = None
        for raw_job in jobs:
            job = required_object(raw_job, "job", "ingest-all")
            name = job.get("job")
            if not isinstance(name, str):
                raise VerificationError("ingest-all returned a job without a name")
            if job.get("ok") is not True:
                detail = job.get("detail")
                failed_jobs.append(f"{name}: {detail or 'unknown failure'}")
            datasets = required_list(
                job.get("datasets"),
                "datasets",
                f"ingest-all job {name}",
            )
            dataset_count += len(datasets)
            for raw_dataset in datasets:
                dataset = required_object(
                    raw_dataset,
                    "dataset",
                    f"ingest-all job {name}",
                )
                if dataset.get("dataset") == "current_weather":
                    fetched_at = dataset.get("fetchedAt")
                    if isinstance(fetched_at, str):
                        current_fetched_at = fetched_at

        if response.status_code != 200 or payload.get("ok") is not True or failed_jobs:
            failures = "; ".join(failed_jobs) or response_detail(response)
            raise VerificationError(
                f"ingest-all returned HTTP {response.status_code}: {failures}"
            )
        if not jobs:
            raise VerificationError("ingest-all returned no jobs")
        if current_fetched_at is None:
            raise VerificationError("ingest-all omitted current-weather results")
        return (
            f"{len(jobs)} jobs passed and reported {dataset_count} datasets",
            current_fetched_at,
        )

    def verify_current_weather(self, expected_fetched_at: str | None) -> str:
        response = self.client.get(
            self.endpoint("/api/weather/current"),
            params={"verification": uuid4().hex},
            headers={"Cache-Control": "no-cache"},
        )
        payload = json_object(response, "current-weather reader")
        required_object(payload.get("data"), "data", "current-weather reader")
        meta = required_object(payload.get("meta"), "meta", "current-weather reader")
        if meta.get("dataset") != "current_weather":
            raise VerificationError("current-weather reader returned the wrong dataset")
        fetched_at = meta.get("fetchedAt")
        if not isinstance(fetched_at, str):
            raise VerificationError("current-weather reader omitted meta.fetchedAt")
        if expected_fetched_at is not None and not matches_mongodb_timestamp(
            expected_fetched_at,
            fetched_at,
        ):
            raise VerificationError(
                "current-weather reader did not return the just-ingested document "
                f"(expected {expected_fetched_at}, got {fetched_at})"
            )
        return f"read current_weather fetched at {fetched_at}"

    def verify_nowcast(self) -> str:
        response = self.client.get(
            self.endpoint("/api/weather/rainfall/nowcast"),
            params={"verification": uuid4().hex},
            headers={"Cache-Control": "no-cache"},
        )
        payload = json_object(response, "rainfall-nowcast index")
        frames = required_list(payload.get("data"), "data", "rainfall-nowcast index")
        meta = required_object(payload.get("meta"), "meta", "rainfall-nowcast index")
        if not frames:
            raise VerificationError("rainfall-nowcast index returned no frames")
        if meta.get("count") != len(frames):
            raise VerificationError("rainfall-nowcast index returned an invalid count")

        frame = required_object(frames[0], "frame", "rainfall-nowcast index")
        frame_path = frame.get("url")
        if not isinstance(frame_path, str):
            raise VerificationError("rainfall-nowcast frame omitted its URL")
        grid_response = self.client.get(self.endpoint(frame_path))
        grid_payload = json_object(grid_response, "rainfall-nowcast grid")
        grid = required_object(
            grid_payload.get("data"),
            "data",
            "rainfall-nowcast grid",
        )
        width = grid.get("width")
        height = grid.get("height")
        values = required_list(grid.get("values"), "values", "rainfall-nowcast grid")
        if (
            not isinstance(width, int)
            or isinstance(width, bool)
            or width <= 0
            or not isinstance(height, int)
            or isinstance(height, bool)
            or height <= 0
        ):
            raise VerificationError("rainfall-nowcast grid has invalid dimensions")
        if len(values) != width * height:
            raise VerificationError(
                "rainfall-nowcast value count does not match its dimensions"
            )
        return f"decoded {len(frames)} frames; first grid is {width}x{height}"

    def verify_radar(self) -> str:
        response = self.client.get(
            self.endpoint("/api/weather/radar"),
            params={"verification": uuid4().hex},
            headers={"Cache-Control": "no-cache"},
        )
        payload = json_object(response, "radar metadata")
        data = required_object(payload.get("data"), "data", "radar metadata")
        image_path = data.get("imageUrl")
        if not isinstance(image_path, str):
            raise VerificationError("radar metadata omitted imageUrl")
        for dimension in ("width", "height"):
            value = data.get(dimension)
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise VerificationError(f"radar metadata has an invalid {dimension}")

        image_response = self.client.get(
            self.endpoint(image_path),
            headers={"Accept": "image/png", "Cache-Control": "no-cache"},
        )
        if image_response.status_code != 200:
            raise VerificationError(
                "radar image returned "
                f"HTTP {image_response.status_code}: {response_detail(image_response)}"
            )
        content_type = image_response.headers.get("content-type", "").partition(";")[0]
        if content_type != "image/png":
            raise VerificationError(
                f"radar image has content type {content_type or 'none'}"
            )
        if not image_response.content.startswith(PNG_SIGNATURE):
            raise VerificationError("radar image does not contain a PNG signature")
        content_length = image_response.headers.get("content-length")
        if content_length is None or content_length != str(len(image_response.content)):
            raise VerificationError("radar image has an invalid Content-Length")
        response_etag = image_response.headers.get("etag")
        if not response_etag:
            raise VerificationError("radar image omitted its ETag")

        conditional = self.client.get(
            self.endpoint(image_path),
            headers={"If-None-Match": response_etag},
        )
        if conditional.status_code != 304:
            raise VerificationError(
                "radar conditional request returned "
                f"HTTP {conditional.status_code} instead of 304"
            )
        return (
            f"read {len(image_response.content)}-byte PNG "
            "and confirmed ETag revalidation"
        )


def run_check(name: str, check: Callable[[], str]) -> bool:
    try:
        detail = check()
    except (VerificationError, httpx.HTTPError) as error:
        print(f"FAIL {name}: {error}")
        return False
    print(f"PASS {name}: {detail}")
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            f"Run an end-to-end smoke test against {DEPLOYMENT_URL}. "
            "CRON_SECRET is read from .env.local."
        )
    )
    parser.add_argument(
        "--skip-ingest",
        action="store_true",
        help="verify existing public reads without calling ingest-all",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30,
        help="timeout in seconds for ordinary requests (default: 30)",
    )
    parser.add_argument(
        "--ingestion-timeout",
        type=float,
        default=300,
        help="timeout in seconds for ingest-all (default: 300)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.timeout <= 0 or args.ingestion_timeout <= 0:
        print("timeouts must be positive", file=sys.stderr)
        return 2
    try:
        verifier = DeploymentVerifier(
            DEPLOYMENT_URL,
            timeout=args.timeout,
            ingestion_timeout=args.ingestion_timeout,
        )
    except (ValueError, httpx.HTTPError) as error:
        print(str(error), file=sys.stderr)
        return 2

    results = []
    current_fetched_at: str | None = None
    try:
        print(f"Verifying {verifier.deployment_url}")
        print(
            "Production /api/health/database is intentionally not tested "
            "(it returns 404)."
        )
        results.append(run_check("application health", verifier.verify_health))

        if not args.skip_ingest:
            try:
                cron_secret = load_cron_secret()
            except ValueError as error:
                print(f"FAIL ingest-all: {error}")
                results.append(False)
            else:
                ingestion_result: tuple[str, str | None] | None = None

                def ingest() -> str:
                    nonlocal ingestion_result
                    ingestion_result = verifier.ingest_all(cron_secret)
                    return ingestion_result[0]

                results.append(run_check("ingest-all", ingest))
                if ingestion_result is not None:
                    current_fetched_at = ingestion_result[1]

        results.append(
            run_check(
                "current-weather read",
                lambda: verifier.verify_current_weather(current_fetched_at),
            )
        )
        results.append(run_check("rainfall-nowcast read", verifier.verify_nowcast))
        results.append(run_check("radar read", verifier.verify_radar))
    except KeyboardInterrupt:
        print("\nVerification interrupted", file=sys.stderr)
        return 130
    finally:
        verifier.close()

    passed = sum(results)
    print(f"\n{passed} of {len(results)} checks passed.")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
