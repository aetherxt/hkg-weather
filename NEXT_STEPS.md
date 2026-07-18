# HKG Weather — Next Steps

Last updated: 18 July 2026

Architecture and storage decisions remain in
[IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md). Upstream formats remain in
[HKO_DATA_API_REFERENCE.md](./HKO_DATA_API_REFERENCE.md).

## Current state

- All planned ingestion groups have protected `POST /api/cron/*` routes.
- cron-job.org is configured and can populate MongoDB continuously.
- MongoDB keeps latest documents and the planned three-day archives.
- `GET /api/weather/current` is the only public weather-data reader currently
  implemented.
- The Next.js application is still a frontend starting point rather than the
  finished weather interface.

## 1. Next step: implement public GET endpoints

The immediate goal is to expose the data already stored in MongoDB through a
stable, read-only API. The frontend should never connect directly to MongoDB or
know about BSON binary storage.

### 1.1 Reader API rules

- Every public route must use `MONGODB_READ_URI`, never the ingestion user.
- Only explicitly supported datasets and query parameters may be read; do not
  expose a generic MongoDB query endpoint.
- Decode stored JSON before returning it.
- Parse stored CSV into typed response objects where the frontend needs
  individual values.
- Return PNG data as its native `image/png` response rather than Base64 inside
  JSON.
- Convert tropical-cyclone KML coordinates to GeoJSON for MapLibre.
- Use camelCase in public JSON, regardless of MongoDB field naming.
- Include `dataset`, `sourceUpdatedAt` and `fetchedAt` in response metadata.
- Return `404` when a valid dataset or station has no stored document, `422`
  for invalid parameters, and `503` when MongoDB is unavailable.
- Successful latest-data responses use the CDN policy from the implementation
  plan. Errors use `Cache-Control: no-store`.
- Timestamp-addressed archive payloads should use an ETag and immutable caching
  because their contents cannot change. Latest image URLs use a short CDN
  lifetime because their contents are replaced.
- Apply bounded archive queries, with a maximum three-day range and a maximum
  result count, so a public request cannot scan the database without limits.

### 1.2 Standard response shape

Latest JSON and parsed CSV endpoints should normally return:

```json
{
  "data": {},
  "meta": {
    "dataset": "current_weather",
    "sourceUpdatedAt": "2026-07-18T10:02:00Z",
    "fetchedAt": "2026-07-18T10:10:00Z"
  }
}
```

List endpoints use an array for `data` and may add `count` to `meta`. Binary
image endpoints return bytes directly and put identifiers, timestamps, bounds
and ETag information in HTTP headers or in a separate JSON index endpoint.

### 1.3 Latest-data endpoints

| Endpoint | Data returned | Notes |
|---|---|---|
| `GET /api/weather/current` | Current weather report | Already implemented; use it as the reader pattern. |
| `GET /api/weather/forecast/local` | Local forecast | Decoded HKO JSON. |
| `GET /api/weather/forecast/nine-day` | Official nine-day forecast | Decoded HKO JSON. |
| `GET /api/weather/warnings` | Warning summary, warning details and special weather tips | Combine the three latest-only documents into one response. Missing inactive warning documents should be represented by empty data, not an application error. |
| `GET /api/weather/rainfall/stations` | Past-hour automatic-station rainfall | Decoded HKO JSON. |
| `GET /api/weather/regional/temperature` | Latest one-minute station temperatures | Parse the stored CSV into station/time/value objects. |
| `GET /api/weather/regional/wind` | Latest ten-minute wind, speed and maximum gust | Parse the stored CSV into station/time/value objects. |
| `GET /api/weather/lampposts` | Latest readings for all configured lampposts | Join stored payloads with labels and coordinates from the JSON configuration. |
| `GET /api/weather/lampposts/{lamppostId}/{deviceId}` | Latest reading for one configured lamppost device | Reject devices outside the configuration. |
| `GET /api/weather/stations` | The 16 configured OCF stations | Return station codes and labels from configuration. |
| `GET /api/weather/stations/{stationCode}/forecast` | One station's complete OCF nine-day forecast | Validate the station against `ocf_stations.json`. |
| `GET /api/weather/models` | Earth Weather model labels and current cycles | Combine model configuration with the stored latest cycle metadata. |
| `GET /api/weather/tropical-cyclones` | All currently active tracks | Return storm metadata and GeoJSON coordinates; an empty list is a successful response. |

### 1.4 Map-data endpoints

| Endpoint | Data returned | Notes |
|---|---|---|
| `GET /api/weather/rainfall/nowcast` | Latest rainfall-grid index and valid times | Return dimensions, bounds, update time and URLs/identifiers for each forecast frame. |
| `GET /api/weather/rainfall/nowcast/{validTime}` | One numerical rainfall grid | Return a compact numerical representation suitable for a Web Worker, Canvas and WebGL. Do not render or store map tiles. |
| `GET /api/weather/radar` | Latest radar-frame metadata | Return observation time, bounds and a stable image URL. |
| `GET /api/weather/radar/image` | Latest radar PNG | Return native PNG bytes. |
| `GET /api/weather/models/{modelId}/rainfall` | Latest model-rainfall metadata | Return model cycle, lead time, valid time, raster dimensions and image URL. |
| `GET /api/weather/models/{modelId}/rainfall/image` | Latest encoded model-rainfall PNG | Return the original stored PNG bytes. Decoding its internal numerical/geographic representation remains separate work. |

For the rainfall-nowcast grid, begin with a straightforward JSON contract:

```json
{
  "data": {
    "updatedAt": "2026-07-18T10:00:00+08:00",
    "validAt": "2026-07-18T10:30:00+08:00",
    "bounds": {"north": 0, "south": 0, "east": 0, "west": 0},
    "width": 0,
    "height": 0,
    "values": []
  },
  "meta": {}
}
```

The final bounds, grid ordering and missing-value convention must be derived
from the HKO CSV and covered by tests before the frontend depends on them. If
JSON size or parsing becomes a measured bottleneck, replace only the `values`
transport with a compact binary format while preserving the endpoint's
metadata contract.

### 1.5 Archive endpoints

Archive access is needed for forecast-versus-observation comparison. Implement
it after the corresponding latest endpoint is stable.

| Endpoint | Purpose |
|---|---|
| `GET /api/weather/history/rainfall/stations?from=&to=` | Observed station rainfall within the three-day window. |
| `GET /api/weather/history/rainfall/nowcast?from=&to=` | Available archived nowcast issue and valid times. |
| `GET /api/weather/history/rainfall/nowcast/{issueTime}/{validTime}` | Numerical grid from one archived forecast. |
| `GET /api/weather/history/radar?from=&to=` | Archived radar-frame index. |
| `GET /api/weather/history/radar/{observedAt}/image` | One timestamped radar PNG. |
| `GET /api/weather/history/stations/{stationCode}/forecast?from=&to=` | Archived OCF forecasts for a configured station. |
| `GET /api/weather/history/models/{modelId}/rainfall?from=&to=` | Archived Earth Weather rainfall-frame metadata. |
| `GET /api/weather/history/models/{modelId}/rainfall/{validAt}/image` | One timestamped stored model raster. |

The first archive response should be an index containing timestamps and stable
URLs. Large payloads and images are fetched individually only when the user
selects a frame.

### 1.6 Backend implementation order

1. Extract the current-weather-specific MongoDB reader into reusable JSON,
   parsed-CSV and binary read helpers.
2. Define shared Pydantic response metadata, list and error models.
3. Add local forecast, nine-day forecast and combined warning endpoints.
4. Add station rainfall, regional temperature, regional wind and lamppost
   endpoints.
5. Add OCF station-list and station-forecast endpoints.
6. Add Earth Weather model-cycle and tropical-cyclone endpoints.
7. Add rainfall-nowcast parsing plus radar and model image endpoints.
8. Add bounded archive index and timestamped payload endpoints.
9. Document every public route in `README.md` and expose it in FastAPI's
   generated OpenAPI schema.

Each endpoint needs tests for a successful read, missing data, malformed stored
data, invalid path/query parameters, database failure and cache headers. Binary
routes additionally need content-type, content-length and ETag tests.

### 1.7 GET-endpoint completion criteria

This step is complete when:

- every latest document required by the planned interface is accessible
  through a typed public route;
- map indexes return enough metadata to position and select stored frames;
- raw PNG payloads are served directly without Base64 encoding;
- the frontend does not need MongoDB field names or knowledge of BSON;
- all endpoints use the reader account and pass backend tests and Ruff;
- deployed smoke tests confirm MongoDB access, CDN headers and response sizes;
- the OpenAPI page accurately describes all public response contracts.

## 2. Add the frontend data layer

After the GET contracts are stable:

1. Add TypeScript types matching the OpenAPI response models.
2. Create one small API client module for same-origin `/api/weather/*` calls.
3. Separate server-rendered initial data from client-side timeline and map
   interactions.
4. Add consistent loading, unavailable, stale-data and retry states.
5. Display source-update time separately from the application's fetch time.
6. Add frontend tests using stored response fixtures rather than live HKO
   calls.

Do not duplicate HKO parsing logic in React components. Components should
receive normalized API data.

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
5. Render numerical rainfall grids with Canvas/WebGL and geographic bounds.
6. Keep weather data layers independent of the basemap so they can be toggled,
   reordered and compared.
7. Test pan, zoom, resize, mobile gestures and high-DPI displays.

## 5. Add weather map layers

Add layers in increasing order of uncertainty:

1. Regional weather stations and smart lamppost markers.
2. Numerical HKO gridded rainfall nowcast.
3. Radar PNG overlay using its stored geographic bounds.
4. Active tropical-cyclone GeoJSON tracks.
5. Earth Weather rainfall rasters after verifying their encoding, projection,
   colour scale and bounds.
6. Additional Earth Weather fields only after the rainfall pipeline is proven.

Every layer needs a source timestamp, valid time, legend, units and a visible
unavailable state. Internal OCF and Earth Weather feeds must fail independently
without taking down official HKO observations or forecasts.

## 6. Build forecast comparison

Use the existing three-day archive to compare what was predicted with what was
later observed:

1. Align forecasts by `issueTime`, `validAt` and lead time.
2. Align observations by station or grid location and observation interval.
3. Let the user select a past valid time and switch between forecast, radar and
   observed station rainfall.
4. Preserve the distinction between quantitative station observations and
   radar imagery used for visual comparison.
5. Add station temperature comparisons between OCF predictions and regional
   observations where station mapping is reliable.
6. Introduce calculated error metrics only after the alignment rules have
   fixture-based tests.

## 7. Harden and verify the complete application

1. Run Python tests and Ruff, then frontend linting, type checking and build.
2. Add API contract fixtures for every official and internal upstream format.
3. Add local end-to-end tests through `vercel dev` using MongoDB test data.
4. Verify Vercel response caching and ensure cron responses are never cached.
5. Add frontend error monitoring and backend structured logs without secrets or
   full upstream payloads.
6. Review MongoDB TTL deletion and storage usage against the free-cluster
   budget.
7. Verify cron failure notifications and periodically test `ingest-all`
   manually.
8. Check accessibility, keyboard navigation, mobile layout and map fallbacks.
9. Document deployment and rollback checks in `README.md`.

## 8. Later options

- Add other Earth Weather fields after rainfall is decoded and stable.
- Add forecast verification summaries beyond the rolling three-day viewer.
- Move large immutable images to object storage only if MongoDB or response-size
  limits become a measured problem.
- Introduce a compact binary grid format only if profiling shows JSON transfer
  or browser parsing is too slow.
- Add multilingual output after the English data contracts and interface are
  stable.
