from pathlib import Path

import httpx

from scripts.configure_cron_jobs import (
    matching_jobs,
    parse_env_file,
    plan_update,
    response_detail,
)


def test_parse_env_file_reads_quoted_secret(tmp_path: Path) -> None:
    env_file = tmp_path / ".env.local"
    env_file.write_text(
        'MONGODB_DATABASE="example"\nCRON_SECRET="secret/value+1="\n',
        encoding="utf-8",
    )

    assert parse_env_file(env_file, "CRON_SECRET") == "secret/value+1="


def test_matching_jobs_filters_domain_and_ingest_all() -> None:
    prefix = "https://hkgweather.vercel.app/api/cron/"
    jobs = [
        {"jobId": 1, "title": "Radar", "url": f"{prefix}radar-128"},
        {"jobId": 2, "title": "Batch", "url": f"{prefix}ingest-all"},
        {
            "jobId": 3,
            "title": "Other",
            "url": "https://example.com/api/cron/radar-128",
        },
    ]

    assert matching_jobs(jobs, prefix) == [jobs[0]]


def test_plan_update_preserves_existing_headers_and_body() -> None:
    job = {
        "jobId": 123,
        "title": "Radar",
        "url": "https://hkgweather.vercel.app/api/cron/radar-128",
        "requestMethod": 0,
        "saveResponses": False,
        "extendedData": {
            "headers": {
                "Content-Type": "application/json",
                "authorization": "Bearer old-secret",
            },
            "body": "existing body",
        },
    }

    update = plan_update(job, "new-secret")

    assert update.changes == (
        "method GET -> POST",
        "replace Authorization header",
        "enable saved responses",
    )
    assert update.patch == {
        "job": {
            "requestMethod": 1,
            "saveResponses": True,
            "extendedData": {
                "headers": {
                    "Content-Type": "application/json",
                    "Authorization": "Bearer new-secret",
                },
                "body": "existing body",
            },
        }
    }


def test_plan_update_reports_already_configured() -> None:
    job = {
        "jobId": 123,
        "title": "Radar",
        "url": "https://hkgweather.vercel.app/api/cron/radar-128",
        "requestMethod": 1,
        "saveResponses": True,
        "extendedData": {
            "headers": {"Authorization": "Bearer current-secret"},
            "body": "",
        },
    }

    assert plan_update(job, "current-secret").changes == ()


def test_response_detail_reports_dataset_count() -> None:
    response = httpx.Response(
        200,
        json={"ok": True, "datasets": [{"dataset": "one"}]},
    )

    assert response_detail(response) == "ok; 1 datasets"


def test_response_detail_reports_api_error() -> None:
    response = httpx.Response(401, json={"detail": "Unauthorized"})

    assert response_detail(response) == "Unauthorized"
