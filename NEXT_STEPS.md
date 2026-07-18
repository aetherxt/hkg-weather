# HKG Weather — Next Steps

Last updated: 18 July 2026

Architecture and storage decisions remain in
[IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md). Upstream formats remain in
[HKO_DATA_API_REFERENCE.md](./HKO_DATA_API_REFERENCE.md). The complete route
catalogue and operational commands are in [README.md](./README.md).

## Current state

- All planned ingestion groups have protected `POST /api/cron/*` routes and
  cron-job.org can populate MongoDB continuously.
- MongoDB maintains replaceable latest documents and the planned rolling
  three-day archives with TTL expiry.
- The public read API is complete: 27 typed `GET /api/weather/*` route patterns
  cover latest data, map data and archives.
- Every public database read uses `MONGODB_READ_URI`; ingestion credentials are
  confined to protected cron routes.
- Stored JSON, CSV, PNG and KML payloads are decoded or normalized by the
  backend. The frontend does not need MongoDB field names, BSON handling or HKO
  parsing logic.
- The deployed API passed the complete production smoke-test matrix: 27 of 27
  weather GET routes, CDN revalidation, immutable payloads, ETags, PNG checks
  and representative validation errors.
- The backend passes 61 tests, Ruff and OpenAPI generation.
- The Next.js application remains a frontend starting point rather than the
  finished weather interface.

## 1. Completed backend foundation

### 1.1 Ingestion and storage

The application stores official HKO feeds plus the selected internal OCF,
Earth Weather, radar and tropical-cyclone feeds. Common ingestion services
validate upstream responses, preserve original bytes, maintain latest
documents and insert bounded archive records.

Archive indexes now cover the public access patterns:

- dataset and source-update time;
- dataset and radar observation time;
- dataset, model and valid time;
- dataset and 30-minute archive slot;
- dataset and content hash;
- TTL expiry time.

Every successful dataset write through the shared JSON or raw ingestion
service runs the idempotent index setup. No separate database migration command
is currently required.

### 1.2 Public read API

| Group | Routes | Delivered behavior |
|---|---:|---|
| Latest weather data | 13 | Forecasts, warnings, observations, lampposts, OCF stations, model cycles and active tropical cyclones |
| Map data | 6 | Numerical rainfall grids, radar metadata/PNG and Earth Weather rainfall metadata/PNG |
| Three-day archives | 8 | Bounded indexes and timestamp-addressed rainfall, radar, OCF and model payloads |

The public API provides:

- a consistent `data` and `meta` JSON envelope;
- `dataset`, `sourceUpdatedAt` and `fetchedAt` metadata;
- `count` on list responses;
- camelCase public fields;
- typed regional temperature, wind and gust readings;
- configured labels and coordinates for lamppost and OCF station data;
- north-to-south, west-to-east numerical rainfall grids;
- tropical-cyclone KML converted to GeoJSON;
- native `image/png` responses without Base64 encoding;
- stable URLs for large and timestamp-addressed payloads.

Only configured datasets, stations, devices, models and bounded query ranges
are accepted. The API exposes no generic MongoDB query mechanism.

### 1.3 Errors and caching

- `404` means a supported resource has no stored document.
- `422` means a station, device, model, timestamp or archive range is invalid.
- `503` means MongoDB is unavailable or a stored payload cannot be safely
  decoded.
- All error responses use `Cache-Control: no-store`.
- Latest responses use short Vercel CDN lifetimes with stale revalidation.
- Local and nine-day forecasts use a longer ten-minute CDN lifetime.
- Timestamp-addressed grids and images use one-year immutable caching and
  ETags.
- Conditional image requests support `304 Not Modified`.
- Archive ranges are limited to three days and 512 stored documents.

### 1.4 Production issues resolved

Two problems were found during the first deployed smoke test and fixed:

1. HKO emits anomalous six-field calm-wind CSV rows such as
   `Lamma Island,Calm,Calm,0,`. The backend now normalizes only this known
   pattern to direction `Calm`, speed `null` and the supplied numeric gust,
   while continuing to reject unrelated schema changes.
2. The nowcast archive index originally loaded and sorted all archived grid
   payloads. It now reads timestamp metadata only, uses an indexed query and
   supports older archive documents by deriving their first 30- and 60-minute
   valid times. Individual numerical grids are still fetched only after a
   frame is selected.

The final deployed verification confirmed:

- all 27 public weather route patterns returned their expected success
  responses;
- regional wind returned 30 readings, including three normalized calm rows;
- the nowcast history returned 62 frame references;
- all archive indexes contained data;
- latest and archived PNG signatures, lengths and ETags were valid;
- a repeated current-weather request produced a Vercel CDN hit;
- an ETag revalidation produced `304`;
- a representative invalid model produced an uncached `422`;
- the largest tested response was approximately 231 KB.

## 2. Immediate next step: add the frontend data layer

The backend contracts are stable enough for frontend integration. Build one
small typed boundary between React and `/api/weather/*`; components should not
know about upstream HKO formats.

1. Add TypeScript types matching the OpenAPI response models, starting with
   warnings, current weather, local forecast, nine-day forecast and regional
   observations.
2. Create a same-origin API client module for `/api/weather/*` with shared JSON
   decoding and a small typed error class for `404`, `422` and `503` responses.
3. Keep server-rendered initial page data separate from client-side timeline,
   station-selection and map interactions.
4. Model loading, unavailable, stale and retry states consistently across all
   sections.
5. Display `sourceUpdatedAt` separately from `fetchedAt`; source time is the
   weather observation or forecast time, while fetch time records ingestion.
6. Add checked-in response fixtures captured from the normalized application
   API. Frontend tests must not call live HKO or MongoDB services.
7. Add frontend lint, type-check and production-build commands to the standard
   verification workflow.

The frontend data layer is complete when a page can load the first non-map
weather sections through typed functions, handle each API error class, and run
tests entirely from fixtures.

## 3. Build the first usable page

Create the non-map information hierarchy before the complex visual layers:

1. Replace the default Next.js page and metadata.
2. Add the page shell, responsive navigation and update-status indicator.
3. Show active warnings and special weather tips first.
4. Add current conditions, local forecast and official nine-day forecast.
5. Add regional observations, station rainfall and smart-lamppost readings.
6. Add OCF station selection and the station-specific nine-day temperature and
   precipitation view.

The page must remain useful when map data or an internal HKO feed is
temporarily unavailable.

## 4. Add the interactive map foundation

1. Install and initialize MapLibre GL JS in a client-only map component.
2. Select a Hong Kong basemap and confirm its attribution and usage terms.
3. Establish shared layer controls, legend placement, timestamps and timeline
   controls.
4. Move large grid parsing and colour conversion into a Web Worker.
5. Render numerical rainfall grids with Canvas or WebGL using the API-provided
   grid ordering and geographic bounds.
6. Keep weather layers independent of the basemap so they can be toggled,
   reordered and compared.
7. Test pan, zoom, resize, mobile gestures and high-DPI displays.

## 5. Add weather map layers

Add layers in increasing order of uncertainty:

1. Regional weather stations and smart-lamppost markers.
2. Numerical HKO gridded rainfall nowcast.
3. Radar PNG overlay using its stored geographic bounds.
4. Active tropical-cyclone GeoJSON tracks.
5. Earth Weather rainfall rasters after verifying their internal encoding,
   projection, colour scale and bounds.
6. Additional Earth Weather fields only after rainfall is proven.

Every layer needs a source timestamp, valid time, legend, units and a visible
unavailable state. Internal OCF and Earth Weather feeds must fail independently
without taking down official HKO observations or forecasts.

## 6. Build forecast comparison

Use the existing three-day archive to compare predictions with later
observations:

1. Align forecasts by `issueTime`, `validAt` and lead time.
2. Align observations by station or grid location and observation interval.
3. Let the user select a past valid time and switch between forecast, radar and
   observed station rainfall.
4. Preserve the distinction between quantitative station observations and
   radar imagery used for visual comparison.
5. Add station-temperature comparisons between OCF predictions and regional
   observations only where station mapping is reliable.
6. Introduce calculated error metrics only after alignment rules have
   fixture-based tests.

## 7. Harden and verify the complete application

1. Run Python tests and Ruff, then frontend linting, type checking and build.
2. Expand API contract fixtures for every official and internal upstream
   format.
3. Add local end-to-end tests through `vercel dev` using MongoDB test data.
4. Keep deployed smoke tests for all public GET routes and confirm cron
   responses remain uncached.
5. Add frontend error monitoring and backend structured logs without secrets
   or full upstream payloads.
6. Review MongoDB TTL deletion, index size and total storage against the free
   cluster budget.
7. Verify cron failure notifications and periodically test `ingest-all`
   manually.
8. Check accessibility, keyboard navigation, mobile layout and map fallbacks.
9. Document deployment and rollback checks in `README.md`.

## 8. Later options

- Add other Earth Weather fields after rainfall is decoded and stable.
- Add forecast-verification summaries beyond the rolling three-day viewer.
- Move large immutable images to object storage only if MongoDB or response
  limits become a measured problem.
- Introduce a compact binary grid format only if profiling shows JSON transfer
  or browser parsing is too slow.
- Add multilingual output after the English data contracts and interface are
  stable.
