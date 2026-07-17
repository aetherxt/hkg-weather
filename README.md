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
    "sourceUpdatedAt": "2026-07-17T09:02:00Z",
    "fetchedAt": "2026-07-17T09:19:00Z"
  }
}
```

Successful responses are cached by Vercel for five minutes with background
revalidation. Browsers revalidate their own copies, and error responses are
never cached.

## Official HKO ingestion routes

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

The smart-lamppost route validates and loads the JSON configuration when it is
called. Changes take effect after the updated application is deployed.

Run the isolated backend checks with:

```bash
cd backend
source .venv/bin/activate
ruff check app tests
pytest -q
```
