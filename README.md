# hkg-weather
More detailed weather site for Hong Kong, based on HKO data

## Local development

Vercel Services runs the Next.js frontend and FastAPI backend together on one
local origin.

Install the frontend dependencies:

```bash
cd web
npm install
cd ..
```

Create the Python environment and install the backend dependencies:

The FastAPI backend reads MongoDB settings from either the repository-level
`.env.local` file or the existing `web/.env.local` file.

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
cd ..
```

Run both services from the repository root:

```bash
npx vercel dev -L
```

The local endpoints are:

- Next.js frontend: <http://localhost:3000>
- FastAPI health: <http://localhost:3000/api/health>
- MongoDB health: <http://localhost:3000/api/health/database>

To check both MongoDB users directly without starting the web applications:

```bash
cd backend
source .venv/bin/activate
python -m scripts.check_database
```

The frontend can call Python with same-origin URLs such as `/api/health`, so no
separate backend hostname or browser CORS configuration is required.

## Deployment

The repository deploys as one Vercel Services project:

- project root directory: the repository root (leave the setting empty);
- framework preset: `Services`;
- `web/`: Next.js frontend service;
- `backend/`: FastAPI backend service;
- `/api/*`: routed to FastAPI;
- all other paths: routed to Next.js.

Add `MONGODB_INGEST_URI`, `MONGODB_READ_URI`, `MONGODB_DATABASE`, and
`CRON_SECRET` to the Vercel project's environment variables. Scheduled jobs
will call protected `/api/cron/*` endpoints on the same deployment domain.

Smart-lamppost selections and map metadata are stored in
`backend/app/data/smart_lamppost_devices.json`. Edit that version-controlled
file to add or remove devices; no smart-lamppost environment variable is
required. The current selection is:

- `50148:01` — Central;
- `27357:01` — Wan Chai;
- `AB3301:01` — Tsim Sha Tsui / Jordan;
- `DF3644:01` — Kowloon Bay / Choi Hung.

OCF station selections are stored in `backend/app/data/ocf_stations.json`.
All 16 full nine-day OCF stations are selected. Urban experimental stations
with shorter three-day forecasts remain excluded. The OCF ingestion route
fetches at most four stations concurrently. OCF and Earth Weather are internal
website feeds rather than versioned public APIs, so their cron routes validate
every response before replacing stored data.

## Current-weather ingestion

`POST /api/cron/current-weather` authenticates with
`Authorization: Bearer <CRON_SECRET>`, fetches the HKO current-weather report,
and writes the raw response to MongoDB. It refreshes the `latest` document on
every successful call and idempotently retains changed content in `archive`
for three days.

To test it locally without placing the secret in shell history, start FastAPI
in one terminal:

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

Then call it from another terminal while the VPN is disabled:

```bash
read -rsp "Cron secret: " CRON_SECRET
curl --fail-with-body --request POST \
  --header "Authorization: Bearer ${CRON_SECRET}" \
  http://127.0.0.1:8000/api/cron/current-weather
unset CRON_SECRET
```

Read the stored report through the public, read-only endpoint:

```bash
curl --fail-with-body http://127.0.0.1:8000/api/weather/current
```

The response contains the decoded original HKO payload and storage metadata:

```json
{
  "data": {},
  "meta": {
    "dataset": "current_weather",
    "sourceUpdatedAt": "2026-07-17T09:02:00Z",
    "fetchedAt": "2026-07-17T09:19:00Z"
  }
}
```

Successful responses are cached by Vercel for five minutes with background
revalidation. Browsers revalidate their own copies, and error responses are
never cached.

## Public weather read routes

All public readers use `MONGODB_READ_URI`. JSON responses use a `data` and
`meta` envelope; readers include `dataset`, `sourceUpdatedAt` and
`fetchedAt` in `meta`, and list readers also include `count`. Stored JSON is
decoded, regional CSV values are typed, OCF and lamppost fields are normalized
to camelCase, and tropical-cyclone KML is returned as GeoJSON.

| Route | Response |
|---|---|
| `GET /api/weather/current` | Current weather report |
| `GET /api/weather/forecast/local` | Local weather forecast |
| `GET /api/weather/forecast/nine-day` | Official nine-day forecast |
| `GET /api/weather/warnings` | Warning summary, details and special weather tips |
| `GET /api/weather/rainfall/stations` | Past-hour automatic-station rainfall |
| `GET /api/weather/regional/temperature` | Typed latest station temperatures |
| `GET /api/weather/regional/wind` | Typed latest station wind and gust readings |
| `GET /api/weather/lampposts` | All available configured lamppost readings |
| `GET /api/weather/lampposts/{lamppostId}/{deviceId}` | One configured lamppost device |
| `GET /api/weather/stations` | Configured OCF station codes and labels |
| `GET /api/weather/stations/{stationCode}/forecast` | One complete OCF station forecast |
| `GET /api/weather/models` | Configured model labels and current cycles |
| `GET /api/weather/tropical-cyclones` | Active storm metadata and GeoJSON tracks |

Map-data readers expose frame metadata separately from larger payloads:

| Route | Response |
|---|---|
| `GET /api/weather/rainfall/nowcast` | Latest grid dimensions, bounds and frame URLs |
| `GET /api/weather/rainfall/nowcast/{validTime}` | One numerical rainfall grid, flattened north-to-south and west-to-east |
| `GET /api/weather/radar` | Latest radar time, bounds, dimensions and image URL |
| `GET /api/weather/radar/image` | Native latest radar PNG |
| `GET /api/weather/models/{modelId}/rainfall` | Latest model rainfall-frame metadata |
| `GET /api/weather/models/{modelId}/rainfall/image` | Native latest encoded model PNG |

Archive index requests require ISO-8601 `from` and `to` query values. The range
must not exceed three days, and a response is limited to 512 stored documents.
Compact timestamps returned in frame URLs are also accepted by timestamped
routes.

| Route | Response |
|---|---|
| `GET /api/weather/history/rainfall/stations?from=&to=` | Archived station-rainfall observations |
| `GET /api/weather/history/rainfall/nowcast?from=&to=` | Archived nowcast issue/valid-time index |
| `GET /api/weather/history/rainfall/nowcast/{issueTime}/{validTime}` | One immutable archived numerical grid |
| `GET /api/weather/history/radar?from=&to=` | Archived radar-frame index |
| `GET /api/weather/history/radar/{observedAt}/image` | One immutable archived radar PNG |
| `GET /api/weather/history/stations/{stationCode}/forecast?from=&to=` | Archived OCF station forecasts |
| `GET /api/weather/history/models/{modelId}/rainfall?from=&to=` | Archived model rainfall-frame index |
| `GET /api/weather/history/models/{modelId}/rainfall/{validAt}/image` | One immutable archived model PNG |

Valid configured resources with no stored payload return `404`; unsupported
identifiers, timestamps and ranges return `422`; invalid stored payloads and
MongoDB failures return `503`. All errors use `Cache-Control: no-store`.
Latest readers use short Vercel CDN caching with stale revalidation. Binary
responses include `Content-Length` and `ETag`; timestamp-addressed payloads use
one-year immutable caching.

## HKO ingestion routes

All ingestion routes use `POST`, require
`Authorization: Bearer <CRON_SECRET>`, and return `Cache-Control: no-store`.

| Route | Data stored |
|---|---|
| `/api/cron/current-weather` | Current weather, latest plus 3-day archive |
| `/api/cron/local-forecast` | Local forecast, latest plus 3-day archive |
| `/api/cron/nine-day-forecast` | Nine-day forecast, latest plus 3-day archive |
| `/api/cron/warnings` | Warning summary, warning information and special tips, latest only |
| `/api/cron/station-rainfall` | Past-hour station rainfall, latest plus 3-day archive |
| `/api/cron/rainfall-nowcast` | Complete latest CSV and first two forecast periods in one archive slot per 30 minutes |
| `/api/cron/regional-weather` | Regional temperature and wind/gust CSVs, latest plus 3-day archive |
| `/api/cron/smart-lampposts` | One latest and archived document per configured device |
| `/api/cron/ocf-station-forecasts` | One latest and 3-day archived OCF forecast per configured station |
| `/api/cron/earth-weather-cycles` | Latest cycle metadata for each configured Earth Weather model |
| `/api/cron/earth-weather-rainfall` | Nearest future surface-rainfall raster for each rainfall-capable Earth Weather model, latest plus 3-day archive |
| `/api/cron/radar-128` | Latest 128 km radar PNG and geographic bounds, with one archive entry per 30-minute slot |
| `/api/cron/tropical-cyclones` | Current official tropical-cyclone track XML per active cyclone, latest plus 3-day archive |
| `/api/cron/ingest-all` | Manually run every configured ingestion source and return a per-job result; do not schedule this route as a cron job |

The internal-feed routes use the same Bearer secret as the official-feed
routes. OCF station data is stored under IDs such as
`ocf_station_forecast:HKO`; Earth Weather cycle metadata is stored under IDs
such as `earth_weather_model_cycle:ec`, and rainfall rasters use IDs such as
`earth_weather_rainfall:ec`. A tropical-cyclone request is successful with an
empty `datasets` array and `activeCyclones: 0` when HKO reports no active
cyclone.

After deployment, run all sources once with:

```bash
curl --fail-with-body --request POST \
  --header "Authorization: Bearer $CRON_SECRET" \
  https://hkgweather.vercel.app/api/cron/ingest-all
```

The batch request runs at most three source groups concurrently and returns
HTTP 502 if any group fails. Its response still includes every group so one
failure does not hide the remaining test results. Continue scheduling the
individual source routes in cron-job.org; the batch route is for manual tests.

The smart-lamppost route validates and loads the JSON configuration when it is
called. Changes take effect after the updated application is deployed.

### Bulk-configure cron-job.org

Use the included configurator instead of editing every cron job manually. It
selects only jobs whose URL starts with
`https://hkgweather.vercel.app/api/cron/`, always excludes `ingest-all`, merges
the application Bearer header with existing custom headers, changes the method
to `POST`, and enables saved responses. Schedules, enabled states and
notifications are not changed.

First create an API key in cron-job.org. Run a dry-run from the repository root:

```bash
backend/.venv/bin/python backend/scripts/configure_cron_jobs.py
```

The script reads `CRON_SECRET` from the environment, `.env.local`, or
`web/.env.local`, and privately prompts for the cron-job.org API key. Review the
displayed job list, then apply it and immediately run every matched endpoint:

```bash
backend/.venv/bin/python backend/scripts/configure_cron_jobs.py --apply
```

The test calls are sent directly to each configured URL with `POST` and the
Bearer secret, then reported as PASS/FAIL with the HTTP status and a short
response summary. They run sequentially to avoid overloading the backend. To
update cron-job.org without running the endpoints, add `--no-run`.

Neither secret is printed or saved by the script. The optional
`CRON_JOB_ORG_API_KEY` environment variable can supply the API key for
non-interactive use; do not commit it.

Run the isolated backend checks with:

```bash
cd backend
source .venv/bin/activate
ruff check app tests
pytest -q
```

## Archive identity/index migration

Archive records use one of two explicit policies:

- `content`: unique by `dataset`, `document_id` and `content_hash`;
- `slot`: unique by `dataset`, `document_id` and `archive_slot`.

The migration from the original archive indexes must be run once against the
live database. It scans every retained archive record's metadata, repairs
missing or invalid `document_id` and `archive_policy` values, creates the new
partial unique/query indexes, and then removes the conflicting legacy indexes.
It does not replace or delete weather payloads.

Pause all cron-job.org ingestion jobs and deploy the matching application code
before applying the migration. Then, from a machine whose IP is permitted by
MongoDB Atlas, run:

```bash
cd backend
source .venv/bin/activate
python -m scripts.migrate_archive_identity
python -m scripts.migrate_archive_identity --apply
```

The first command is a dry run. Review its database name, backfill counts and
legacy-index list before running the second command and confirming the change.
After it succeeds, run the dry run again; it should report no remaining fields
or legacy indexes to migrate. Re-enable the cron jobs, manually run
`/api/cron/ingest-all`, and verify that new archive records contain both
`document_id` and `archive_policy`.
