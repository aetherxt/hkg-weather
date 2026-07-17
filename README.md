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
