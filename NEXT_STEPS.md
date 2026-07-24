# HKG Weather — Next Steps

Last updated: 19 July 2026

Architecture and storage decisions remain in
[IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md). Upstream formats remain in
[HKO_DATA_API_REFERENCE.md](./HKO_DATA_API_REFERENCE.md). The complete route
catalogue and operational commands are in [README.md](./README.md).

## Current state

- All planned ingestion groups have protected `POST /api/cron/*` routes and
  cron-job.org can populate MongoDB continuously.
- MongoDB maintains replaceable latest documents and the planned rolling
  three-day archives with TTL expiry.
- The public read API is complete: 28 typed `GET /api/weather/*` route patterns
  cover an aggregate dashboard snapshot, focused latest data, map data and
  archives.
- Every public database read uses `MONGODB_READ_URI`; ingestion credentials are
  confined to protected cron routes.
- Stored JSON, CSV, PNG and KML payloads are decoded or normalized by the
  backend. The frontend does not need MongoDB field names, BSON handling or HKO
  parsing logic.
- The deployed API passed the complete production smoke-test matrix: 27 of 27
  weather GET routes, CDN revalidation, immutable payloads, ETags, PNG checks
  and representative validation errors.
- The backend passes 95 tests, Ruff and OpenAPI generation.
- `backend/scripts/verify_deployment.py` provides a repeatable post-deployment
  smoke test for health, authenticated ingestion, the current-weather reader,
  a decoded nowcast grid, and radar PNG/ETag handling.
- The Next.js application loads all non-map home-page data through one cached
  aggregate route. Visible tabs refresh one snapshot every ten minutes, focus
  refreshes are rate-limited, and hidden tabs do not poll.
- Reduced captures from the normalized application API drive 11 offline
  frontend tests; `npm run verify` runs lint, type checking, tests and a
  production build.
- The home page now has a responsive weather-dashboard prototype with current
  condition typography, warning presentation, UV and air-quality rows, desktop
  detail navigation, bottom page navigation and HKO-icon-driven weather-scene
  animation scaffolding.
- The visible dashboard still uses sample values. The typed current-weather
  response is available to the page loader but has not yet replaced those
  samples.

## 1. Frontend data layer (complete)

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

The page-facing loader can load the first non-map weather sections through
typed functions, handles each API error class independently, and is covered
entirely by checked-in fixtures.

## 2. Immediate next step: implement current weather data

Replace the hard-coded current-condition samples with the normalized response
from `GET /api/weather/current`. Keep this change focused on the top current
weather area; warnings and forecast data can be connected in the following
milestones.

1. Make `web/app/page.tsx` call `loadInitialWeatherForPage()` and pass the
   current-weather section state into the dashboard.
2. Add a small current-weather view-model adapter. It should select the Hong
   Kong Observatory temperature and humidity readings when present, choose a
   documented fallback when that station is missing, and keep missing values
   as `null` rather than inventing zeroes.
3. Derive the displayed condition from the HKO `icon` array through one
   checked-in icon-code map. Preserve the full array because HKO can return a
   primary weather icon together with descriptive modifiers.
4. Pass the same icon array into `WeatherScene` so the text colour, condition
   label and entrance animation are driven by one source of truth.
5. Derive rainfall from the current report deliberately. Prefer the entry
   marked `main: "TRUE"`; document the fallback if HKO omits it, and do not mix
   district bulletin rainfall with automatic-station rainfall.
6. Read UV from the current report when available. Render a compact unavailable
   value outside the daytime reporting period instead of keeping the sample.
7. Display the observation or icon update time near the current conditions and
   expose stale data using `sourceUpdatedAt`. Do not present `fetchedAt` as the
   weather observation time.
8. Handle all current section states in the existing layout:
   `loading`, `ready`, `stale`, `retrying` and `unavailable`. The page shell and
   navigation must remain usable when the current feed fails.
9. Remove the hard-coded `29`, `Showers`, `80`, `3`, UV value and icon code only
   after their data-backed equivalents render successfully.
10. Add fixture-based tests for station selection, multiple icon codes, missing
    temperature or humidity, absent UV, missing main rainfall and stale source
    time.
11. Verify the result at desktop and mobile widths, with reduced motion enabled,
    and run `npm run verify` before moving to the next milestone.

Completion means a server-rendered visit to the home page shows current HKO
data without client-side layout replacement, and a current-feed failure has a
clear isolated fallback.

## 3. Frontend warnings and advisory data

1. Replace `sampleWarnings` with the loaded warning-summary section.
2. Keep cancelled entries out of the active list and remove the Warnings detail
   tab when no active warnings remain.
3. Preserve the existing `No warnings` empty state and ensure it is not confused
   with an unavailable warning feed.
4. Connect issue and update action labels to their corresponding timestamps;
   show dates only when action and expiry dates differ.
5. Add special weather tips, rainstorm reminders and tropical-cyclone messages
   from the current-weather response without duplicating official warnings.
6. Add loading, stale and unavailable warning states that do not shift the
   current-weather block unexpectedly.
7. Add fixtures covering issue, update, cancel-only, empty, multiple-warning and
   malformed-time cases.

## 4. Frontend current-detail interactions

1. Replace the current sample detail-panel copy with values from the same view
   models used by the left-hand summary.
2. Make the Temperature panel explain observation place, record time, humidity
   and recent range where data exists.
3. Make the Rainfall panel identify the reporting interval and district; link
   station rainfall only when its different dataset is clearly labelled.
4. Make the UV and air-quality panel distinguish current HKO UV observations
   from the air-quality source and timestamp each independently.
5. Preserve the shared click behavior between left summary sections and the
   desktop mini navigation, including replaying the top-to-bottom reveal.
6. Define a mobile detail pattern instead of merely hiding the desktop panel.
   Prefer an inline disclosure or bottom sheet that remains keyboard accessible.
7. Close or redirect an active panel when its navigation item disappears, such
   as when the final warning is cancelled.

## 5. Frontend forecast page

1. Connect the blank Forecast page to local forecast and official nine-day
   forecast data from the existing initial loader.
2. Present the local forecast period, description, outlook, general situation,
   tropical-cyclone information and fire-danger information with separate
   unavailable states.
3. Build a responsive nine-day list using minimum and maximum temperature,
   humidity range, wind, weather description, `ForecastIcon` and qualitative
   `PSR` without converting the probability category into a fabricated number.
4. Reuse the HKO icon map and visual weather groups from the current page.
5. Add day selection and a compact expanded view without requiring a map.
6. Keep source update times visible and prevent a failed internal station feed
   from hiding the official forecast.
7. Add fixtures for all PSR categories, missing optional fields and mixed day
   and night icon codes.

## 6. Frontend observations and station views

1. Add regional temperature, wind and gust summaries with observation times.
2. Add past-hour automatic-station rainfall while keeping it distinct from the
   district rainfall bulletin used by current conditions.
3. Add smart-lamppost readings with clear device names, units and unavailable
   states.
4. Add OCF station selection and persist the selection locally without making
   it a prerequisite for the official Hong Kong forecast.
5. Build the OCF nine-day temperature and precipitation view, retaining the
   original chance-of-rain category strings.
6. Add searchable or grouped station selection only after the basic station
   view is usable with keyboard and touch input.

## 7. Frontend visual and interaction refinement

1. Move all HKO icon labels and scene groups into one tested module shared by
   current conditions and forecasts.
2. Tune weather-scene layers for sunny, partly cloudy, showers, rain intensity,
   thunderstorms, night, wind, fog, mist, haze and temperature modifiers.
3. Keep decorative weather layers non-interactive and hidden from assistive
   technology; respect `prefers-reduced-motion` and avoid hydration-time
   randomness.
4. Add intentional loading skeletons that preserve the final text dimensions.
5. Audit focus order, focus visibility, semantic buttons, tab behavior, colour
   contrast and screen-reader labels.
6. Verify 320 px mobile, common phone widths, tablet, 1024 px desktop and wide
   desktop layouts. Prevent detail panels and fixed navigation from covering
   content at short viewport heights.
7. Add component-level visual checks for empty, long-text, stale, unavailable
   and multiple-warning states.
8. Finalize page metadata, title, description, icons and a no-JavaScript useful
   server-rendered state.

The non-map interface must remain useful when map data or an internal HKO feed
is temporarily unavailable.

## 8. Add the interactive map foundation

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

## 9. Add weather map layers

Add layers in increasing order of uncertainty:

1. Regional weather stations and smart-lamppost markers.
2. Numerical HKO gridded rainfall nowcast.
3. Radar PNG overlay using its stored geographic bounds.
4. Active tropical-cyclone GeoJSON tracks and 70% Potential Track Area polygons.
5. Earth Weather rainfall rasters and the matching ECMWF surface `UV` wind
   vector raster after verifying their internal encoding,
   projection, colour scale and bounds.
6. Additional Earth Weather fields only after rainfall and ECMWF wind are
   proven.

Every layer needs a source timestamp, valid time, legend, units and a visible
unavailable state. Internal OCF and Earth Weather feeds must fail independently
without taking down official HKO observations or forecasts.

## 10. Build forecast comparison

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

## 11. Harden and verify the complete application

1. Run Python tests and Ruff, then frontend linting, type checking and build.
2. Expand API contract fixtures for every official and internal upstream
   format.
3. Add local end-to-end tests through `vercel dev` using MongoDB test data.
4. Keep the complete deployed smoke matrix for all public GET routes, use the
   scripted deployment verifier for the core ingestion/read path, and confirm
   cron responses remain uncached.
5. Add frontend error monitoring and backend structured logs without secrets
   or full upstream payloads.
6. Review MongoDB TTL deletion, index size and total storage against the free
   cluster budget.
7. Verify cron failure notifications and periodically test `ingest-all`
   manually.
8. Repeat the accessibility, keyboard, reduced-motion, mobile-layout and map-
   fallback checks as part of release verification.
9. Document deployment and rollback checks in `README.md`.

## 12. Later options

- Add other Earth Weather fields after rainfall and ECMWF wind decoding are
  stable.
- Add forecast-verification summaries beyond the rolling three-day viewer.
- Move large immutable images to object storage only if MongoDB or response
  limits become a measured problem.
- Introduce a compact binary grid format only if profiling shows JSON transfer
  or browser parsing is too slow.
- Add multilingual output after the English data contracts and interface are
  stable.

## 13. Astronomical and tidal data

HKO publishes sunrise, moonrise and tidal predictions through separate feeds.
The complete current-year sunrise/sunset and moonrise/moonset CSV tables are
now ingested as latest-only documents. They are not yet exposed through a
public reader or displayed.

### 13.1 Sunrise, sunset, moonrise and moonset

1. The protected `POST /api/cron/astronomical-times` route fetches HKO's
   yearly `SRS` and `MRS` CSV feeds for the current Hong Kong calendar year,
   validates every date and time, and stores both complete tables latest-only.
2. `backend/scripts/configure_cron_jobs.py` creates the enabled annual job when
   absent and enforces its January 1, 01:15 `Asia/Hong_Kong` schedule when it
   already exists.
3. Add a typed read route (`GET /api/weather/astronomical`) returning the daily
   sunrise, sunset, moonrise and moonset values. Keep the response
   independent of the current-weather update cycle.
4. Add TypeScript response types, a client method, a fixture and an entry in
   the initial-page loader.
5. Present today's sunrise and sunset times on the home page — display these
   near the current-condition area, or in a compact footer row that replaces the
   hard-coded sample values.
6. Add moon-phase data later from a separate verified source; `SRS` and `MRS`
   do not contain moon phase.
7. Keep the astronomical feed failure isolated from other weather data and test
   with a checked-in fixture.

### 13.2 Tidal predictions

1. Review the HKO tidal-prediction feed:
   `https://data.weather.gov.hk/weatherAPI/opendata/tide.php`
   with parameters `?lang=en&station=` and a station code.
2. Decide which tide stations to configure. HKO provides predictions for
   multiple locations around Hong Kong (e.g. Chi Ma Wan, Quarry Bay, Tai Miu
   Wan, Tsim Sha Tsui, Waglan Island). Store the selection in a version-
   controlled JSON file under `backend/app/data/` following the
   `smart_lamppost_devices.json` pattern.
3. Define a backend ingestion spec (`ingest_tide_predictions`) that fetches
   daily tide predictions for each configured station.
4. Add a typed read route (`GET /api/weather/tide`) returning a list of daily
   high and low waters with times and heights for each station.
5. Add TypeScript response types, a client method, a fixture and an entry in
   the initial-page loader.
6. Present the next high and low water in a compact readout on the home page,
   or under a new detail-panel section. Label the station and show heights in
   metres.
7. Keep per-station failure independent — a failed Chi Ma Wan fetch should not
   hide Quarry Bay predictions.
8. Add a mobile responsive layout for tide data. Consider a simple timeline or
   small list showing the day's high and low waters rather than a full chart.

These feeds contain scheduled predictions rather than real-time observations.
The astronomical tables have a documented yearly update frequency; tidal
scheduling should be decided when that ingestion is implemented. The frontend
should treat missing astronomical or tidal data as a minor omission—the weather
dashboard must remain functional without them.
