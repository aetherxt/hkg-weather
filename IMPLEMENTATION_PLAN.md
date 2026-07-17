# HKG Weather Web Application — Planning Document

Last updated: 17 July 2026
Endpoint and response-format details: [HKO_DATA_API_REFERENCE.md](./HKO_DATA_API_REFERENCE.md)

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
- JSON datasets use a shared, specification-driven ingestion service for upstream fetching, Pydantic validation, raw-byte hashing, latest/archive writes, retention and API error translation.
- Each JSON source supplies only its dataset identifiers, URL, payload model, source-update-time extractor and archive-retention policy.
- `/api/health` is the public application health endpoint.
- `/api/health/database` checks both MongoDB users during local development and returns 404 in Vercel preview and production deployments.
- MongoDB Atlas Network Access must permit connections from the deployed Vercel service while database authentication remains restricted by the ingestion and reader roles.

### 1.3 API response caching

- Public `GET /api/weather/*` responses use Vercel CDN caching to avoid querying MongoDB once per client.
- Fast-changing observations, warning information and latest-frame indexes use a 30–60 second CDN lifetime.
- Current weather uses a five-minute CDN lifetime; local and nine-day forecasts use a ten-minute lifetime.
- Timestamped map frames use content-specific URLs and long-lived immutable caching.
- Public responses use `stale-while-revalidate` so the CDN can serve a cached response while refreshing it from FastAPI and MongoDB.
- Authenticated `POST /api/cron/*`, health, error and user-specific responses are never cached.
- Public cacheable requests must not include authorization headers or cookies, and non-streaming responses must remain below Vercel's 10 MB CDN response limit.

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

Earth Weather encoded model assets will be retained only as raw upstream inputs where required. Model colours and interactive weather layers will be generated in the browser rather than stored as finished map images.

### 2.4 HKO radar and tropical-cyclone feeds

- 128 km weather-radar KML index and PNG overlays
- Current tropical-cyclone track information
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
- Insert an archive document only when its upstream timestamp or content hash changes.
- Datasets marked `Latest only` replace their current document and never write to the archive collection.
- No archived API record is retained for more than three days.
- Use MongoDB TTL indexes and proactively delete expired documents before archive insertion.
- Do not store generated map tiles, browser-rendered weather layers or OCF-rendered fallback PNGs.
- Retain static station, device and location lookup data as latest-only documents and replace them when their content changes.

### 3.3 Dataset storage policy

| Data | Stored representation | Capture policy | Retention |
|---|---|---|---|
| Past-hour station rainfall | Raw JSON | Save each new observation time; also maintain latest | 3 days |
| Gridded two-hour rainfall nowcast | Raw complete CSV for latest; uncompressed BSON binary containing the first two 30-minute grids for archive | Refresh latest when HKO updates; archive every 30 minutes | Latest plus 3-day archive |
| Current weather report | Raw JSON | Save when update time or content changes; also maintain latest | 3 days |
| Local weather forecast | Raw JSON | Save when update time or content changes; also maintain latest | 3 days |
| Official nine-day forecast | Raw JSON | Save when update time or content changes; also maintain latest | 3 days |
| Warning information | Raw JSON | Replace latest when the warning information changes | Latest only |
| Warning summary | Raw JSON | Replace latest on each changed state, including transition to no warnings | Latest only |
| Special weather tips | Raw JSON | Replace latest on each changed state, including transition to no tips | Latest only |
| Smart-lamppost observations | Raw JSON for the devices selected in `backend/app/data/smart_lamppost_devices.json`: `50148:01` (Central), `27357:01` (Wan Chai), `AB3301:01` (Tsim Sha Tsui/Jordan) and `DF3644:01` (Kowloon Bay/Choi Hung) | Save each new measurement time; also maintain latest | 3 days |
| Regional one-minute mean temperature | Raw CSV | Save each new source time; also maintain latest | 3 days |
| Regional wind, speed and maximum gust | Raw CSV | Save each new source time; also maintain latest | 3 days |
| OCF nine-day station forecasts | Raw JSON response per configured station | Save each new model time; also maintain latest per station | 3 days |
| OCF two-hour rainfall assets | No duplicate archive; use the documented gridded nowcast as the canonical numerical source | OCF assets may be fetched for validation or fallback only | Not stored |
| Earth Weather model-cycle metadata | Raw current-cycle JSON per model | Replace when the model cycle changes | Latest only |
| Earth Weather rainfall | Original encoded surface `RF` PNG for the nearest future valid time, with model, cycle, lead time, valid time and raster dimensions | Maintain one latest frame per rainfall-capable model and archive each changed prediction; defer geographic cropping until the internal raster geometry is decoded reliably | 3 days |
| Other Earth Weather fields | None by default | Fetch on demand unless later added to the storage plan | Not stored |
| 128 km radar | Original PNG plus bounds and observation time from KML | Maintain latest and archive one image every 30 minutes | Latest plus 3-day archive |
| Current tropical-cyclone track | Raw XML | Save each changed track while a cyclone product exists; also maintain latest | 3 days |
| Tropical-cyclone best track | Raw official data used when available for comparison | Fetch on demand or maintain the latest published file | Latest only |

### 3.4 Rainfall archive size

- Each 30-minute archive snapshot keeps the first two forecast grids, covering the forecast available for the following 60 minutes.
- One 128 km radar PNG is archived at the same 30-minute cadence for visual comparison.
- Station rainfall observations are the numerical verification source; radar is used for visual comparison.
- The three-day uncompressed rainfall-forecast archive is approximately 194 MB.
- The three-day radar archive is approximately 10 MB.
- Rainfall forecast, radar, metadata and indexes are expected to use approximately 215–225 MB before the other stored datasets are included.
- Keep total Atlas storage below approximately 400 MB to leave headroom under the 512 MB free-cluster limit.

## 4. Next implementation order

1. Verify local access to both MongoDB users without the VPN. Complete.
2. Add the shared ingestion foundation: validated cron secret, Bearer authentication, runtime HTTP client dependency and reproducible archive indexes. Complete.
3. Implement `POST /api/cron/current-weather` as the first end-to-end ingestion route. Complete and production verified.
4. Implement `GET /api/weather/current` using the read-only MongoDB user, with a five-minute Vercel CDN lifetime and `stale-while-revalidate` caching. Complete and production verified. Apply the dataset-specific caching rules in section 1.3 to subsequent public read routes.
5. Test the complete current-weather pipeline locally, then deploy it. Complete.
6. Configure cron-job.org to call the production ingestion route every 10 minutes with `Authorization: Bearer <CRON_SECRET>`. Complete and verified with an automatic production run.
7. Refactor JSON ingestion into a reusable dataset-specification service without changing the current-weather API or storage format. Complete.
8. Add warning summary, warning information and special weather tips as latest-only datasets using the shared JSON ingestion service. Complete locally; production deployment and live ingestion verification remain.
9. Add the remaining official HKO ingestion feeds before implementing internal OCF, Earth Weather, radar and tropical-cyclone feeds. Complete locally for local forecast, nine-day forecast, station rainfall, gridded rainfall nowcast, regional temperature/wind and configurable smart-lamppost routes.
10. Add OCF station forecasts from a version-controlled station list and latest-only Earth Weather model-cycle metadata. Complete locally; production deployment and live ingestion verification remain.
11. Add the nearest future Earth Weather rainfall raster for every rainfall-capable model, the 128 km radar image/index adapter and active tropical-cyclone track ingestion. Complete locally; production deployment and live ingestion verification remain.
12. Add one protected, manually invoked batch-ingestion route that runs every configured source with bounded concurrency and reports each source independently. Complete locally; do not schedule it as a recurring cron job.
13. Add public read routes for the ingested feeds with the caching policies in section 1.3.

Live MongoDB connectivity and integration checks are run manually by the project owner. Automated backend tests use mocks by default and must not connect to the live database.
