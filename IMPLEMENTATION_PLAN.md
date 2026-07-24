# HKG Weather Web Application — Planning Document

Last updated: 18 July 2026
Endpoint and response-format details: [HKO_DATA_API_REFERENCE.md](./HKO_DATA_API_REFERENCE.md)
Implementation sequence: [NEXT_STEPS.md](./NEXT_STEPS.md)

## 1. Stack

| Area | Choice |
|---|---|
| Web framework | Next.js App Router with TypeScript |
| Hosting | One Vercel Services project containing the Next.js and FastAPI services |
| Backend | Python FastAPI service |
| Backend runtime | Vercel Python runtime, compatible with Python 3.12 and later |
| Database | MongoDB Atlas |
| Database client | Official PyMongo asynchronous driver |
| Map | MapLibre GL JS |
| Weather-layer rendering | Browser-side Canvas and WebGL from numerical grid data |
| Validation | Pydantic |
| Scheduled ingestion | cron-job.org calling protected `/api/cron/*` FastAPI endpoints |
| CDN and response caching | Vercel CDN |

### 1.1 Application and deployment structure

- The repository root is the Vercel project root and contains `vercel.json`.
- The Vercel framework preset is `Services`.
- `web/` is the Next.js frontend service.
- `backend/` is the FastAPI backend service, with `app.main:app` as its entry point.
- `/api/*` requests are routed to FastAPI; all other requests are routed to Next.js.
- Both services deploy and roll back together on the same domain.
- Browser requests to FastAPI use same-origin `/api/*` URLs and do not require CORS.
- The services run together locally with `npx vercel dev -L` from the repository root.
- FastAPI is request-driven on Vercel; no scheduler or permanent worker runs inside the service.
- cron-job.org triggers ingestion by sending authenticated HTTP requests to the deployed `/api/cron/*` routes.

### 1.2 Backend and environment configuration

- Production and preview secrets are stored as Vercel project environment variables.
- Required variables are `MONGODB_INGEST_URI`, `MONGODB_READ_URI`, `MONGODB_DATABASE` and `CRON_SECRET`.
- MongoDB and cron secrets must never use the `NEXT_PUBLIC_` prefix.
- Local MongoDB variables may be stored in the repository-level `.env.local` or the existing `web/.env.local`; both are ignored by Git.
- Pydantic validates backend environment variables without logging their values.
- Python runtime dependencies are defined in `backend/requirements.txt`; pytest and Ruff use dedicated configuration files so Vercel does not treat the backend as a `uv` package project.
- PyMongo creates separate lazy, reusable asynchronous clients for the ingestion and reader users.
- JSON and raw datasets use one shared ingestion core for fetching, hashing,
  latest/archive writes, retention and API error translation. Format-specific
  modules supply only validation and dataset configuration.
- Each JSON source supplies its identifiers, URL, payload model,
  source-update-time extractor and retention policy. CSV, KML and PNG sources
  supply a raw-byte validator and any archive metadata or reduced payload.
- Regional temperature and wind ingestion validates every non-empty row,
  including schema, calendar time, station identity, measurement values and
  consistent observation times, before replacing stored data.
- `storage_read.py` provides reusable latest-document, stored-metadata, JSON,
  CSV and binary readers.
- `weather_reads.py` composes focused latest, map and archive routers. Shared
  response models and read helpers live in `weather_read_models.py` and
  `weather_read_common.py`; gridded-rainfall parsing is isolated in
  `rainfall_nowcast.py`.
- The implemented public API contains 28 `GET /api/weather/*` route patterns:
  one aggregate dashboard route, 13 focused latest-data routes, six map-data
  routes and eight archive routes.
- Public readers decode BSON binary payloads and return camelCase application
  contracts; frontend code never receives MongoDB field names or BSON values.
- `/api/health` is the public application health endpoint.
- `/api/health/database` checks both MongoDB users during local development and returns 404 in Vercel preview and production deployments.
- MongoDB Atlas Network Access must permit connections from the deployed Vercel service while database authentication remains restricted by the ingestion and reader roles.

### 1.3 API response caching

- Public `GET /api/weather/*` responses use Vercel CDN caching to avoid querying MongoDB once per client.
- The aggregate non-map dashboard response and fast-changing observations use
  a five-minute CDN lifetime.
- Current weather uses a five-minute CDN lifetime; local and nine-day forecasts use a ten-minute lifetime.
- The home page loads one aggregate dashboard response, refreshes it at most
  every ten minutes while visible, and performs a focus refresh only when the
  last request is at least five minutes old. Hidden tabs do not poll.
- Timestamped map frames use content-specific URLs and long-lived immutable caching.
- Public responses use `stale-while-revalidate` so the CDN can serve a cached response while refreshing it from FastAPI and MongoDB.
- Authenticated `POST /api/cron/*`, health, error and user-specific responses are never cached.
- Public cacheable requests must not include authorization headers or cookies, and non-streaming responses must remain below Vercel's 10 MB CDN response limit.

### 1.4 Public read API contract

- JSON responses use a `data` and `meta` envelope. Metadata includes `dataset`,
  `sourceUpdatedAt` and `fetchedAt`; list responses also include `count`.
- Supported regional CSV products are parsed into typed station observations.
- Rainfall-nowcast grids expose update and valid times, geographic bounds,
  width, height and row-major numerical values ordered north-to-south and
  west-to-east.
- Radar and Earth Weather image endpoints return native `image/png` bytes.
- Tropical-cyclone track and Potential Track Area KML coordinates are converted
  to GeoJSON. The browser shades the first 72 hours and 72–120 hours separately.
- Configured lamppost and OCF station information is joined with labels and
  coordinates before it reaches the frontend.
- Valid resources without stored data return `404`; invalid identifiers,
  timestamps and ranges return `422`; unavailable storage or malformed stored
  payloads return `503`.
- Errors use `Cache-Control: no-store`.
- Timestamp-addressed archive payloads use content ETags and one-year immutable
  caching. Conditional image reads support `304 Not Modified`.
- Archive queries require a maximum three-day range and return no more than 512
  stored documents.
- The deployed API has passed a complete 27-route production smoke test,
  including CDN hits, PNG validation, ETag revalidation and archive access.

## 2. Data sources

### 2.1 Documented HKO open data

- Rainfall in the past hour from automatic weather stations
- Gridded rainfall nowcast
- Current weather report
- Local weather forecast
- Nine-day weather forecast
- Weather-warning information
- Weather-warning summary
- Special weather tips
- Smart-lamppost meteorological observations
- Latest one-minute mean regional air temperature
- Latest ten-minute mean regional wind direction, wind speed and maximum gust
- Yearly sunrise, sunset, moonrise and moonset tables

Catalogue: <https://www.hko.gov.hk/en/abouthko/opendata_intro.htm>

### 2.2 HKO OCF internal feeds

- Nine-day station forecast:
  - hourly temperature;
  - hourly relative humidity;
  - hourly wind direction and speed;
  - three-hourly weather icons;
  - daily minimum and maximum temperature;
  - daily probability of precipitation.
- Two-hour rainfall-nowcast frame index and raw rainfall-grid files, if the internal format is decoded

Viewer: <https://maps.weather.gov.hk/ocf/>

These are internal website feeds rather than versioned public APIs.
Configured station codes are kept in
`backend/app/data/ocf_stations.json`. Store all 16 full nine-day station feeds;
exclude the shorter urban experimental station feeds.

The primary rainfall-map source will be the documented numerical gridded-rainfall-nowcast feed. OCF-rendered PNGs may be used for comparison or fallback, but will not be stored as application data. Weather overlays will be generated in the browser from numerical values using Canvas or WebGL.

### 2.3 HKO Earth Weather internal feeds

Models:

- ECMWF
- ECMWF-AIFS
- Fengwu
- Fuxi
- Pangu
- AAMC-WRF

Products, where supported:

- Rainfall
- Temperature
- Relative humidity
- Wind
- Wind gust
- Mean sea-level pressure
- Upper-air fields
- Pressure and geopotential contours
- Potential-thunderstorm overlay

Viewer: <https://maps.weather.gov.hk/wxviewer/index.html?lang=en>

These are internal viewer assets rather than versioned public APIs.

Earth Weather encoded model assets will be retained only as raw upstream inputs where required. This includes the ECMWF surface `UV` raster used for wind particles. Model colours and interactive weather layers will be generated in the browser rather than stored as finished map images.

### 2.4 HKO radar and tropical-cyclone feeds

- 128 km weather-radar KML index and PNG overlays
- Current tropical-cyclone track information
- Current 70% Potential Track Area for each active tropical cyclone
- Tropical-cyclone best-track data for comparison when available

## 3. Storage

### 3.1 MongoDB Atlas layout

- Cluster: `hkg-weather`
- Live database: `hkg-weather-live`
  - Initial collection: `latest`
- Test database: `hkg-weather-test`
  - Initial collection: `test`
- Database users:
  - ingestion user: `readWrite` on `hkg-weather-live`, used only by protected ingestion and cron routes;
  - reader user: `read` on `hkg-weather-live`, used by application read routes and ordinary local development;
  - optional test user: `readWrite` on `hkg-weather-test`, used by automated integration tests and destructive database tests.
- Application setup code will create the remaining collections and indexes so their definitions are reproducible.

### 3.2 Common rules

- Store upstream JSON, CSV, XML and image payloads as BSON binary data with their original content type.
- Do not Base64-encode binary payloads.
- Preserve `fetched_at`, `source_updated_at` or observation time, `valid_at`, `lead_minutes`, `source_url`, `byte_size`, `content_hash` and `expires_at` where applicable.
- Keep one replaceable latest document for products needed by the live page.
- Compare exact raw content hashes before validation and full replacement.
  Unchanged content-addressed payloads and repeat calls within the same archive
  slot update only `fetched_at`; a new slot still receives its required
  archive record even when its bytes match the previous slot.
- Insert an archive document only when its upstream timestamp or content hash changes.
- Datasets marked `Latest only` replace their current document and never write to the archive collection.
- No archived API record is retained for more than three days.
- Store `document_id` on every archive record so stations, devices, models and
  cyclones can be selected without decoding unrelated payloads.
- Mark each archive record with an explicit `archive_policy`: content-addressed
  records are unique by dataset, document identity and content hash;
  slot-addressed records are unique by dataset, document identity and archive
  slot. Separate partial unique indexes enforce the two policies.
- Use a MongoDB TTL index to remove expired archive documents.
- Maintain query indexes beginning with dataset and document identity for
  source-update time, radar observation time and model valid time.
- Store the first two nowcast valid times as archive metadata so an archive
  index can be returned without reading every numerical grid payload.
- Validate every nowcast row and complete grid before storage, including finite
  values, consistent issue time, chronological periods, unique coordinates and
  rectangular grids with a consistent coordinate domain.
- Do not store generated map tiles, browser-rendered weather layers or OCF-rendered fallback PNGs.
- Retain static station, device and location lookup data as latest-only documents and replace them when their content changes.

### 3.3 Dataset storage policy

| Data | Stored representation | Capture policy | Retention |
|---|---|---|---|
| Past-hour station rainfall | Raw JSON | Save each new observation time; also maintain latest | 3 days |
| Gridded two-hour rainfall nowcast | Raw complete CSV and upstream ETag for latest; uncompressed BSON binary containing the first two 30-minute grids plus their valid-time metadata for archive | Check the ETag with a one-byte conditional request; fetch changed files in four version-locked parallel ranges within a 50-second network budget; archive every 30 minutes | Latest plus 3-day archive |
| Current weather report | Raw JSON | Save when update time or content changes; also maintain latest | 3 days |
| Local weather forecast | Raw JSON | Save when update time or content changes; also maintain latest | 3 days |
| Official nine-day forecast | Raw JSON | Save when update time or content changes; also maintain latest | 3 days |
| Warning information | Raw JSON | Replace latest when the warning information changes | Latest only |
| Warning summary | Raw JSON | Replace latest on each changed state, including transition to no warnings | Latest only |
| Special weather tips | Raw JSON | Replace latest on each changed state, including transition to no tips | Latest only |
| Smart-lamppost observations | Raw JSON for the devices selected in `backend/app/data/smart_lamppost_devices.json`: `50148:01` (Central), `27357:01` (Wan Chai), `AB3301:01` (Tsim Sha Tsui/Jordan) and `DF3644:01` (Kowloon Bay/Choi Hung) | Save each new measurement time; also maintain latest | 3 days |
| Regional one-minute mean temperature | Raw CSV | Save each new source time; also maintain latest | 3 days |
| Regional wind, speed and maximum gust | Raw CSV; recognize HKO's observed six-field calm-row anomaly during validation and normalize it in the public adapter while preserving original bytes | Save each new source time; also maintain latest | 3 days |
| Sunrise, sunset, moonrise and moonset | Two complete raw yearly CSV tables (`SRS` and `MRS`) | Replace the latest documents when the selected calendar year or upstream content changes | Latest only |
| OCF nine-day station forecasts | Raw JSON response per configured station | Save each new model time; also maintain latest per station | 3 days |
| OCF two-hour rainfall assets | No duplicate archive; use the documented gridded nowcast as the canonical numerical source | OCF assets may be fetched for validation or fallback only | Not stored |
| Earth Weather model-cycle metadata | Raw current-cycle JSON per model | Replace when the model cycle changes | Latest only |
| Earth Weather rainfall | Original encoded surface `RF` PNG for the nearest future valid time, with model, cycle, lead time, valid time and raster dimensions | Maintain one latest frame per rainfall-capable model and archive each changed prediction; defer geographic cropping until the internal raster geometry is decoded reliably | 3 days |
| ECMWF wind vectors | Original encoded surface `UV` PNG for the same cycle, lead time and valid time selected by the Earth Weather rainfall job; store encoded and vector-grid dimensions plus component/unit metadata | Maintain one latest ECMWF frame and archive each changed prediction; decode and animate particles in the browser | 3 days |
| Other Earth Weather fields | None by default | Fetch on demand unless later added to the storage plan | Not stored |
| 128 km radar | Original PNG plus bounds and observation time from KML | Maintain latest and archive one image every 30 minutes | Latest plus 3-day archive |
| Current tropical-cyclone track | Raw XML | Save each changed track while a cyclone product exists; also maintain latest | 3 days |
| Tropical-cyclone Potential Track Area | Raw KML per active cyclone; expose only the two filled HKO cone polygons as GeoJSON and ignore auxiliary circle outlines | Fetch with the existing tropical-cyclone job, save each changed area and maintain latest while available | 3 days |
| Tropical-cyclone best track | Raw official data used when available for comparison | Fetch on demand or maintain the latest published file | Latest only |

### 3.4 Rainfall archive size

- Each 30-minute archive snapshot keeps the first two forecast grids, covering the forecast available for the following 60 minutes.
- One 128 km radar PNG is archived at the same 30-minute cadence for visual comparison.
- Station rainfall observations are the numerical verification source; radar is used for visual comparison.
- The three-day uncompressed rainfall-forecast archive is approximately 194 MB.
- The three-day radar archive is approximately 10 MB.
- Rainfall forecast, radar, metadata and indexes are expected to use approximately 215–225 MB before the other stored datasets are included.
- Keep total Atlas storage below approximately 400 MB to leave headroom under the 512 MB free-cluster limit.

## 4. Project file structure

```text
hkg-weather/
├── .env.example                         # Environment-variable template
├── .gitignore                           # Repository-wide ignore rules
├── HKO_DATA_API_REFERENCE.md            # Upstream API and response reference
├── IMPLEMENTATION_PLAN.md               # Living application plan
├── NEXT_STEPS.md                        # Ordered implementation work
├── README.md                            # Setup, development and deployment guide
├── vercel.json                          # Vercel Services and /api routing configuration
├── backend/
│   ├── app/
│   │   ├── __init__.py                  # Python application package
│   │   ├── auth.py                      # CRON_SECRET authentication
│   │   ├── config.py                    # Environment and application settings
│   │   ├── database.py                  # MongoDB ingestion and reader clients
│   │   ├── internal_feeds.py            # OCF, Earth Weather, radar and cyclone feeds
│   │   ├── ingestion.py                 # Shared fetch, storage and archive pipeline
│   │   ├── json_ingestion.py            # JSON validation adapter
│   │   ├── main.py                      # FastAPI entrypoint, health and ingestion routes
│   │   ├── official_feeds.py            # Documented HKO feed definitions
│   │   ├── rainfall_nowcast.py           # Gridded-rainfall parser and validator
│   │   ├── raw_ingestion.py             # Raw-payload validation adapter
│   │   ├── storage.py                   # MongoDB indexes and archive policies
│   │   ├── storage_read.py              # Shared JSON, CSV, binary and metadata readers
│   │   ├── upstream.py                  # Shared upstream HTTP client
│   │   ├── weather_reads.py             # Public weather router composition
│   │   ├── weather_latest_reads.py      # Latest observation and forecast routes
│   │   ├── weather_map_reads.py         # Latest numerical grid and image routes
│   │   ├── weather_archive_reads.py     # Bounded archive routes
│   │   ├── weather_read_common.py       # Shared reader helpers
│   │   ├── weather_read_models.py       # Public response models
│   │   └── data/
│   │       ├── ocf_stations.json        # All 16 stored OCF stations
│   │       └── smart_lamppost_devices.json
│   │                                       # Selected smart-lamppost devices
│   ├── scripts/
│   │   ├── __init__.py                  # Script package
│   │   ├── check_database.py            # Local MongoDB connectivity check
│   │   ├── configure_cron_jobs.py       # Bulk cron-job.org setup and testing
│   │   └── verify_deployment.py          # Deployed ingestion/read smoke test
│   ├── tests/
│   │   ├── test_auth.py
│   │   ├── test_configure_cron_jobs.py
│   │   ├── test_current_weather.py
│   │   ├── test_current_weather_route.py
│   │   ├── test_health.py
│   │   ├── test_internal_feeds.py
│   │   ├── test_json_ingestion.py
│   │   ├── test_official_feed_routes.py
│   │   ├── test_official_feeds.py
│   │   ├── test_raw_ingestion.py
│   │   ├── test_storage.py
│   │   ├── test_verify_deployment.py
│   │   └── test_weather_read_routes.py
│   ├── pytest.ini                       # Pytest configuration
│   ├── requirements.txt                 # Production dependencies
│   ├── requirements-dev.txt             # Development and test dependencies
│   └── ruff.toml                        # Python lint configuration
└── web/
    ├── app/
    │   ├── favicon.ico                  # Site icon
    │   ├── globals.css                  # Global and Tailwind styles
    │   ├── layout.tsx                   # Next.js root layout
    │   └── page.tsx                     # Home page
    ├── public/                          # Static browser assets
    ├── .gitignore                       # Next.js-specific ignore rules
    ├── eslint.config.mjs                # Frontend lint configuration
    ├── next.config.ts                   # Next.js configuration
    ├── package.json                     # Frontend scripts and dependencies
    ├── package-lock.json                # Locked npm dependency versions
    ├── postcss.config.mjs               # Tailwind/PostCSS configuration
    └── tsconfig.json                    # TypeScript configuration
```

The planned source tree excludes generated and machine-local content such as
`.env.local`, `.vercel/`, `backend/build/`, virtual environments, Python cache
directories, `web/.next/` and `web/node_modules/`. These must not be committed.
