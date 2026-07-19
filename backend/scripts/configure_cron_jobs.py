from __future__ import annotations

import argparse
import ast
import getpass
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

API_ROOT = "https://api.cron-job.org"
DEFAULT_JOB_PREFIX = "https://hkgweather.vercel.app/api/cron/"
POST_METHOD = 1
MINIMUM_REQUEST_INTERVAL_SECONDS = 0.25
ASTRONOMICAL_JOB_TITLE = "Astronomical Times"
ASTRONOMICAL_JOB_PATH = "astronomical-times"
ASTRONOMICAL_JOB_SCHEDULE = {
    "timezone": "Asia/Hong_Kong",
    "expiresAt": 0,
    "hours": [1],
    "mdays": [1],
    "minutes": [15],
    "months": [1],
    "wdays": [-1],
}
METHOD_NAMES = {
    0: "GET",
    1: "POST",
    2: "OPTIONS",
    3: "HEAD",
    4: "PUT",
    5: "DELETE",
    6: "TRACE",
    7: "CONNECT",
    8: "PATCH",
}


class CronJobApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class JobUpdate:
    job_id: int
    title: str
    url: str
    changes: tuple[str, ...]
    patch: dict[str, Any]


@dataclass(frozen=True)
class JobCreation:
    title: str
    url: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class JobRunResult:
    title: str
    status_code: int | None
    ok: bool
    detail: str


def parse_env_file(path: Path, name: str) -> str | None:
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
                raise ValueError(f"Invalid {name} value in {path}") from error
            if not isinstance(parsed, str):
                raise ValueError(f"Invalid {name} value in {path}")
            value = parsed
        if value:
            return value
    return None


def load_cron_secret(repository_root: Path) -> str:
    environment_value = os.getenv("CRON_SECRET")
    if environment_value:
        return environment_value

    for path in (
        repository_root / ".env.local",
        repository_root / "web" / ".env.local",
    ):
        value = parse_env_file(path, "CRON_SECRET")
        if value:
            return value

    value = getpass.getpass("Application CRON_SECRET: ")
    if not value:
        raise ValueError("CRON_SECRET is required")
    return value


def matching_jobs(
    jobs: list[dict[str, Any]],
    job_prefix: str,
) -> list[dict[str, Any]]:
    matches = []
    for job in jobs:
        url = job.get("url")
        if not isinstance(url, str) or not url.startswith(job_prefix):
            continue
        if url.removesuffix("/").endswith("/ingest-all"):
            continue
        matches.append(job)
    return sorted(matches, key=lambda job: str(job.get("title", "")).lower())


def plan_update(
    job: dict[str, Any],
    cron_secret: str,
    *,
    expected_schedule: dict[str, Any] | None = None,
) -> JobUpdate:
    try:
        job_id = int(job["jobId"])
        title = str(job["title"])
        url = str(job["url"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("cron-job.org returned an invalid job") from error

    extended_data = job.get("extendedData")
    if not isinstance(extended_data, dict):
        extended_data = {}
    existing_headers = extended_data.get("headers")
    if not isinstance(existing_headers, dict):
        existing_headers = {}

    expected_authorization = f"Bearer {cron_secret}"
    current_authorization = next(
        (
            value
            for key, value in existing_headers.items()
            if str(key).lower() == "authorization"
        ),
        None,
    )
    merged_headers = {
        str(key): value
        for key, value in existing_headers.items()
        if str(key).lower() != "authorization"
    }
    merged_headers["Authorization"] = expected_authorization

    changes = []
    current_method = job.get("requestMethod", 0)
    if current_method != POST_METHOD:
        method_name = METHOD_NAMES.get(current_method, str(current_method))
        changes.append(f"method {method_name} -> POST")
    if current_authorization != expected_authorization:
        changes.append(
            "replace Authorization header"
            if current_authorization is not None
            else "add Authorization header"
        )
    if job.get("saveResponses") is not True:
        changes.append("enable saved responses")
    if expected_schedule is not None and job.get("schedule") != expected_schedule:
        changes.append("set annual Hong Kong schedule")

    job_patch = {
        "requestMethod": POST_METHOD,
        "saveResponses": True,
        "extendedData": {
            "headers": merged_headers,
            "body": str(extended_data.get("body", "")),
        },
    }
    if expected_schedule is not None:
        job_patch["schedule"] = expected_schedule
    patch = {"job": job_patch}
    return JobUpdate(
        job_id=job_id,
        title=title,
        url=url,
        changes=tuple(changes),
        patch=patch,
    )


def astronomical_job_url(job_prefix: str) -> str:
    return f"{job_prefix.rstrip('/')}/{ASTRONOMICAL_JOB_PATH}"


def plan_astronomical_creation(
    jobs: list[dict[str, Any]],
    job_prefix: str,
    cron_secret: str,
) -> JobCreation | None:
    url = astronomical_job_url(job_prefix)
    if any(str(job.get("url", "")).rstrip("/") == url for job in jobs):
        return None
    return JobCreation(
        title=ASTRONOMICAL_JOB_TITLE,
        url=url,
        payload={
            "job": {
                "title": ASTRONOMICAL_JOB_TITLE,
                "url": url,
                "enabled": True,
                "saveResponses": True,
                "requestMethod": POST_METHOD,
                "schedule": ASTRONOMICAL_JOB_SCHEDULE,
                "extendedData": {
                    "headers": {
                        "Authorization": f"Bearer {cron_secret}",
                    },
                    "body": "",
                },
            }
        },
    )


class CronJobClient:
    def __init__(self, api_key: str) -> None:
        self._client = httpx.Client(
            base_url=API_ROOT,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        self._last_request_started = 0.0

    def close(self) -> None:
        self._client.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        elapsed = time.monotonic() - self._last_request_started
        if elapsed < MINIMUM_REQUEST_INTERVAL_SECONDS:
            time.sleep(MINIMUM_REQUEST_INTERVAL_SECONDS - elapsed)
        self._last_request_started = time.monotonic()

        try:
            response = self._client.request(method, path, json=payload)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as error:
            status = ""
            if isinstance(error, httpx.HTTPStatusError):
                status = f" ({error.response.status_code})"
            raise CronJobApiError(
                f"cron-job.org API request failed: {method} {path}{status}"
            ) from error

    def list_jobs(self) -> list[dict[str, Any]]:
        response = self._request("GET", "/jobs")
        jobs = response.get("jobs")
        if not isinstance(jobs, list):
            raise CronJobApiError("cron-job.org returned an invalid job list")
        return jobs

    def get_job(self, job_id: int) -> dict[str, Any]:
        response = self._request("GET", f"/jobs/{job_id}")
        details = response.get("jobDetails")
        if not isinstance(details, dict):
            raise CronJobApiError("cron-job.org returned invalid job details")
        return details

    def patch_job(self, update: JobUpdate) -> None:
        self._request("PATCH", f"/jobs/{update.job_id}", payload=update.patch)

    def create_job(self, creation: JobCreation) -> int:
        response = self._request("PUT", "/jobs", payload=creation.payload)
        try:
            return int(response["jobId"])
        except (KeyError, TypeError, ValueError) as error:
            raise CronJobApiError(
                "cron-job.org returned an invalid job creation response"
            ) from error


def response_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        text = response.text.strip().replace("\n", " ")
        return text[:300] or "empty response"

    if not isinstance(payload, dict):
        return "JSON response"
    if isinstance(payload.get("detail"), str):
        return payload["detail"][:300]
    if isinstance(payload.get("datasets"), list):
        return f"ok; {len(payload['datasets'])} datasets"
    if isinstance(payload.get("jobs"), list):
        return f"ok; {len(payload['jobs'])} jobs"
    dataset = payload.get("dataset")
    if isinstance(dataset, str):
        return f"ok; {dataset}"
    return "ok" if payload.get("ok") is True else "JSON response"


def run_configured_jobs(
    jobs: list[JobUpdate],
    cron_secret: str,
) -> list[JobRunResult]:
    results = []
    timeout = httpx.Timeout(180, connect=30)
    headers = {
        "Authorization": f"Bearer {cron_secret}",
        "User-Agent": "hkg-weather-cron-configurator/1.0",
    }
    with httpx.Client(headers=headers, timeout=timeout) as client:
        for job in jobs:
            print(f"Running {job.title} ...", flush=True)
            try:
                response = client.post(job.url)
                try:
                    body = response.json()
                except ValueError:
                    body = None
                application_ok = not (
                    isinstance(body, dict) and body.get("ok") is False
                )
                results.append(
                    JobRunResult(
                        title=job.title,
                        status_code=response.status_code,
                        ok=response.is_success and application_ok,
                        detail=response_detail(response),
                    )
                )
            except httpx.HTTPError as error:
                results.append(
                    JobRunResult(
                        title=job.title,
                        status_code=None,
                        ok=False,
                        detail=type(error).__name__,
                    )
                )
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create required cron-job.org jobs and configure project jobs to "
            "use POST and the application Bearer secret. Dry-run is the default."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="apply the displayed changes after confirmation",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="skip the confirmation prompt (requires --apply)",
    )
    parser.add_argument(
        "--no-run",
        action="store_true",
        help="apply configuration without immediately running every matched job",
    )
    parser.add_argument(
        "--job-prefix",
        default=DEFAULT_JOB_PREFIX,
        help="only update jobs whose URL begins with this value",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.yes and not args.apply:
        print("--yes requires --apply", file=sys.stderr)
        return 2

    repository_root = Path(__file__).resolve().parents[2]
    try:
        cron_secret = load_cron_secret(repository_root)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2

    api_key = os.getenv("CRON_JOB_ORG_API_KEY") or getpass.getpass(
        "cron-job.org API key: "
    )
    if not api_key:
        print("cron-job.org API key is required", file=sys.stderr)
        return 2

    client = CronJobClient(api_key)
    try:
        listed_jobs = client.list_jobs()
        selected_jobs = matching_jobs(listed_jobs, args.job_prefix)
        creation = plan_astronomical_creation(
            listed_jobs,
            args.job_prefix,
            cron_secret,
        )
        if not selected_jobs and creation is None:
            print(f"No jobs matched {args.job_prefix}")
            return 1

        updates = []
        astronomical_url = astronomical_job_url(args.job_prefix)
        for job in selected_jobs:
            details = client.get_job(int(job["jobId"]))
            expected_schedule = (
                ASTRONOMICAL_JOB_SCHEDULE
                if str(details.get("url", "")).rstrip("/") == astronomical_url
                else None
            )
            updates.append(
                plan_update(
                    details,
                    cron_secret,
                    expected_schedule=expected_schedule,
                )
            )
        pending = [update for update in updates if update.changes]

        print(f"Matched {len(updates)} jobs (ingest-all is always excluded).")
        for update in updates:
            description = ", ".join(update.changes) or "already configured"
            print(f"- {update.title}: {description}")
        if creation is not None:
            print(
                f"- {creation.title}: create enabled annual job at "
                "01:15 Asia/Hong_Kong on January 1"
            )

        if not pending and creation is None:
            print("No configuration changes are required.")
        if not args.apply:
            print("\nDry run only. Re-run with --apply to update these jobs.")
            return 0

        if not args.yes:
            action = f"apply changes to {len(pending)} jobs"
            if creation is not None:
                action += " and create 1 job"
            if not args.no_run:
                action += (
                    f" and run all {len(updates) + int(creation is not None)} "
                    "configured endpoints"
                )
            confirmation = input(f"Proceed: {action}? [y/N] ")
            if confirmation.strip().lower() != "y":
                print("No changes applied.")
                return 0

        for update in pending:
            client.patch_job(update)
            print(f"Updated {update.title}")

        if creation is not None:
            job_id = client.create_job(creation)
            updates.append(
                JobUpdate(
                    job_id=job_id,
                    title=creation.title,
                    url=creation.url,
                    changes=(),
                    patch={},
                )
            )
            print(f"Created {creation.title}")

        print(
            f"Successfully updated {len(pending)} jobs and created "
            f"{int(creation is not None)} jobs."
        )

        if args.no_run:
            return 0

        print("\nRunning each endpoint directly with the configured Bearer secret.")
        run_results = run_configured_jobs(updates, cron_secret)
        print("\nTest results:")
        for result in run_results:
            status = result.status_code if result.status_code is not None else "ERROR"
            outcome = "PASS" if result.ok else "FAIL"
            print(f"- {outcome} {status} {result.title}: {result.detail}")
        failures = [result for result in run_results if not result.ok]
        if failures:
            print(f"{len(failures)} of {len(run_results)} endpoint tests failed.")
            return 1
        print(f"All {len(run_results)} endpoint tests passed.")
        return 0
    except (CronJobApiError, KeyError, TypeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
