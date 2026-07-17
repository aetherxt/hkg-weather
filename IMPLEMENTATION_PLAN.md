# Better Weather Web Application — Planning Document

Last updated: 16 July 2026  
Endpoint and response-format details: [HKO_DATA_API_REFERENCE.md](./HKO_DATA_API_REFERENCE.md)

## 1. Stack

| Area | Choice |
|---|---|
| Web framework | Next.js App Router with TypeScript |
| Hosting | Vercel |
| Backend | Next.js Route Handlers using the Node.js runtime |
| Database | MongoDB Atlas |
| Database client | Official MongoDB Node.js driver |
| Map | MapLibre GL JS |
| Weather-layer rendering | Browser-side Canvas and WebGL from numerical grid data |
| Validation | Zod |
| Scheduled ingestion | cron-job.org calling a protected Vercel Route Handler |
| CDN and response caching | Vercel CDN |

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
- Lightning count over Hong Kong territory in the past hour
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
- One-hour lightning-nowcast frame index and raw affected-grid JSON data

Viewer: <https://maps.weather.gov.hk/ocf/>

These are internal website feeds rather than versioned public APIs.

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

### 3.1 Common rules

- Store upstream JSON, CSV, XML and image payloads as BSON binary data with their original content type.
- Do not Base64-encode binary payloads.
- Preserve `fetchedAt`, upstream update or observation time, forecast valid time, forecast lead time, source URL, byte size and content hash.
- Keep one replaceable latest document for products needed by the live page.
- Insert an archive document only when its upstream timestamp or content hash changes.
- No archived API record or derived verification record is retained for more than three days.
- Use MongoDB TTL indexes and proactively delete expired documents before archive insertion.
- Do not store generated map tiles, browser-rendered weather layers or OCF-rendered fallback PNGs.
- Retain static station, device and location lookup data as latest-only documents and replace them when their content changes.

### 3.2 Dataset storage policy

| Data | Stored representation | Capture policy | Retention |
|---|---|---|---|
| Past-hour station rainfall | Raw JSON | Save each new observation time; also maintain latest | 3 days |
| Gridded two-hour rainfall nowcast | Raw complete CSV for latest; uncompressed BSON binary containing the first two 30-minute grids for archive | Refresh latest when HKO updates; archive every 30 minutes | Latest plus 3-day archive |
| Current weather report | Raw JSON | Save when update time or content changes; also maintain latest | 3 days |
| Local weather forecast | Raw JSON | Save when update time or content changes; also maintain latest | 3 days |
| Official nine-day forecast | Raw JSON | Save when update time or content changes; also maintain latest | 3 days |
| Warning information | Raw JSON | Save each changed warning state; also maintain latest | 3 days |
| Warning summary | Raw JSON | Save each changed warning state, including transition to no warnings; also maintain latest | 3 days |
| Special weather tips | Raw JSON | Save each changed tips state, including transition to no tips; also maintain latest | 3 days |
| Past-hour lightning count | Raw JSON | Save each new hourly period; also maintain latest | 3 days |
| Smart-lamppost observations | Raw JSON per configured lamppost and device | Save each new measurement time; also maintain latest | 3 days |
| Regional one-minute mean temperature | Raw CSV | Save each new source time; also maintain latest | 3 days |
| Regional wind, speed and maximum gust | Raw CSV | Save each new source time; also maintain latest | 3 days |
| OCF nine-day station forecasts | Raw JSON response per configured station | Save each new model time; also maintain latest per station | 3 days |
| OCF two-hour rainfall assets | No duplicate archive; use the documented gridded nowcast as the canonical numerical source | OCF assets may be fetched for validation or fallback only | Not stored |
| OCF one-hour lightning nowcast | Raw current index and affected-grid JSON | Maintain latest for live display | Latest only |
| Earth Weather model-cycle metadata | Raw current-cycle JSON per model | Replace when the model cycle changes | Latest only |
| Earth Weather rainfall | Losslessly cropped surface `RF` raster using the two-hour-nowcast geographic bounds | Save supported rainfall frames for each new model cycle; also maintain latest cycle | 3 days |
| Other Earth Weather fields | None by default | Fetch on demand unless later added to the storage plan | Not stored |
| 128 km radar | Original PNG plus bounds and observation time from KML | Maintain latest and archive one image every 30 minutes | Latest plus 3-day archive |
| Current tropical-cyclone track | Raw XML | Save each changed track while a cyclone product exists; also maintain latest | 3 days |
| Tropical-cyclone best track | Raw official data used when available for comparison | Fetch on demand or maintain the latest published file | Latest only |
| Forecast-verification results | Compact BSON containing forecast identity, observation identity and calculated errors | Calculate after the matching observation arrives | 3 days |

### 3.3 Rainfall archive size

- Each 30-minute archive snapshot keeps the first two forecast grids, covering the forecast available for the following 60 minutes.
- One 128 km radar PNG is archived at the same 30-minute cadence for visual comparison.
- Station rainfall observations are the numerical verification source; radar is used for visual comparison.
- The three-day uncompressed rainfall-forecast archive is approximately 194 MB.
- The three-day radar archive is approximately 10 MB.
- Rainfall forecast, radar, metadata and indexes are expected to use approximately 215–225 MB before the other stored datasets are included.
- Keep total Atlas storage below approximately 400 MB to leave headroom under the 512 MB free-cluster limit.
