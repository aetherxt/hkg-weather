# Hong Kong Observatory Data and Model Feed Reference

Last reviewed: 17 July 2026
Primary catalogue: <https://www.hko.gov.hk/en/abouthko/opendata_intro.htm>

## 1. Purpose and scope

This document describes how to call and interpret the following Hong Kong Observatory (HKO) datasets:

- rainfall in the past hour from automatic weather stations;
- gridded rainfall nowcast;
- current weather report;
- local weather forecast;
- 9-day weather forecast;
- weather warning information;
- weather warning summary;
- special weather tips;
- smart-lamppost meteorological observations;
- regional weather products:
  - latest 1-minute mean air temperature;
  - latest 10-minute mean wind direction, wind speed and maximum gust;
- internal Automatic Regional Weather Forecast (OCF) products:
  - nine-day station forecast, including hourly temperature and daily probability of precipitation;
- prediction-model products displayed by HKO Earth Weather:
  - ECMWF;
  - ECMWF-AIFS;
  - Fengwu;
  - Fuxi;
  - Pangu;
  - AAMC-WRF.

There are two different classes of interface in this document:

1. **Documented HKO open-data interfaces.** These are the preferred interfaces for production applications.
2. **Internal website assets.** These are used by the HKO OCF and Earth Weather web applications but are not documented as stable public APIs. They can change without versioning or advance notice.

No API key or authentication is currently required for the documented endpoints below. All examples use HTTP `GET`.

## 2. Common conventions

### 2.1 Language

Where supported, use the `lang` query parameter:

| Value | Language |
|---|---|
| `en` | English |
| `tc` | Traditional Chinese |
| `sc` | Simplified Chinese |

If omitted, the documented weather APIs default to English.

### 2.2 Time formats

Two time representations are common:

- JSON weather APIs: ISO 8601, such as `2026-07-16T14:45:00+08:00`.
- CSV and table-style feeds: compact Hong Kong time, normally `YYYYMMDDHHmm`, such as `202607161445`.

The Earth Weather model viewer uses UTC model-cycle and valid times in `YYYYMMDDHH` form.

### 2.3 Missing and conditional data

Do not assume every documented property is always present.

- Weather API properties may be omitted when unavailable.
- Some list-like properties can be returned as an empty string rather than an empty array.
- Regional CSV products commonly use `N/A`.
- Past-hour station rainfall can use `M` for missing data.
- Smart-lamppost elements use `////` when a value fails quality control.

Applications should validate values before converting them to numbers.

### 2.4 Basic calling examples

Using `curl`:

```bash
curl "https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=rhrread&lang=en"
```

Using JavaScript:

```js
async function getJson(url) {
  const response = await fetch(url);

  if (!response.ok) {
    throw new Error(`HKO request failed: ${response.status}`);
  }

  return response.json();
}
```

Using Python:

```python
import requests

response = requests.get(
    "https://data.weather.gov.hk/weatherAPI/opendata/weather.php",
    params={"dataType": "rhrread", "lang": "en"},
    timeout=15,
)
response.raise_for_status()
data = response.json()
```

## 3. Endpoint summary

| Dataset | Response | Endpoint or resource |
|---|---|---|
| Past-hour station rainfall | JSON | `https://data.weather.gov.hk/weatherAPI/opendata/hourlyRainfall.php?lang=en` |
| Gridded rainfall nowcast | CSV | `https://data.weather.gov.hk/weatherAPI/hko_data/F3/Gridded_rainfall_nowcast.csv` |
| Current weather | JSON | `https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=rhrread&lang=en` |
| Local forecast | JSON | `https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=flw&lang=en` |
| 9-day forecast | JSON | `https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=fnd&lang=en` |
| Warning information | JSON | `https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=warningInfo&lang=en` |
| Warning summary | JSON | `https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=warnsum&lang=en` |
| Special weather tips | JSON | `https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=swt&lang=en` |
| Smart lamppost | JSON | `https://data.weather.gov.hk/weatherAPI/smart-lamppost/smart-lamppost.php?pi={lamppost}&di={device}` |
| 1-minute temperature | CSV | `https://data.weather.gov.hk/weatherAPI/hko_data/regional-weather/latest_1min_temperature.csv` |
| 10-minute wind and gust | CSV | `https://data.weather.gov.hk/weatherAPI/hko_data/regional-weather/latest_10min_wind.csv` |
| OCF nine-day station forecast | JSON in a file named `.xml` | `https://maps.weather.gov.hk/ocf/dat/{stationCode}.xml` |

## 4. Rainfall in the past hour

### 4.1 Calling method

```http
GET https://data.weather.gov.hk/weatherAPI/opendata/hourlyRainfall.php?lang=en
```

Parameters:

| Parameter | Required | Values | Meaning |
|---|---:|---|---|
| `lang` | No | `en`, `tc`, `sc` | Station-name language; default `en` |

The dataset is normally updated every 15 minutes. The observations are provisional and represent the one-hour period ending at `obsTime`.

### 4.2 Return format

```ts
interface HourlyRainfallResponse {
  obsTime: string;
  hourlyRainfall: Array<{
    automaticWeatherStation: string;
    automaticWeatherStationID: string;
    value: string;
    unit: "mm";
  }>;
}
```

Example:

```json
{
  "obsTime": "2026-07-15T23:15:00+08:00",
  "hourlyRainfall": [
    {
      "automaticWeatherStation": "Lau Fau Shan",
      "automaticWeatherStationID": "RF001",
      "value": "0",
      "unit": "mm"
    },
    {
      "automaticWeatherStation": "Sham Shui Po",
      "automaticWeatherStationID": "RF022",
      "value": "M",
      "unit": "mm"
    }
  ]
}
```

Important parsing rule: `value` is a string, not a guaranteed number. Treat `M` as missing.

## 5. Gridded rainfall nowcast

### 5.1 Calling method

```http
GET https://data.weather.gov.hk/weatherAPI/hko_data/F3/Gridded_rainfall_nowcast.csv
```

This feed is normally updated every 12 minutes. It contains half-hourly accumulated rainfall forecasts up to two hours ahead. It is a comparatively large CSV containing one row per valid time and grid coordinate.

### 5.2 Return format

```csv
Updated Date and Time (in Hong Kong Time),Ending Date and Time (in Hong Kong Time),Latitude (degree),Longitude (degree),Half-hourly Nowcast Accumulated Rainfall (mm)
202607161600,202607161630,23.487,112.956,0.00
202607161600,202607161630,23.487,112.976,0.00
```

Logical row type:

```ts
interface GriddedRainfallRow {
  updatedTime: string;          // YYYYMMDDHHmm, Hong Kong time
  endingTime: string;           // end of half-hour forecast period
  latitude: number;             // degrees
  longitude: number;            // degrees
  accumulatedRainfall: number;  // millimetres during the half-hour
}
```

To obtain the forecast nearest a coordinate:

1. Group rows by `endingTime`.
2. Within each group, select the closest latitude/longitude grid point.
3. Interpret the rainfall value as accumulation during that half-hour, not instantaneous rainfall intensity.

## 6. Current weather report

### 6.1 Calling method

```http
GET https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=rhrread&lang=en
```

This is the broadest current-conditions response. It combines regional temperature, humidity, rainfall, lightning, weather icons, UV information and conditional messages. It is normally updated hourly and when information changes.

### 6.2 Return format

```ts
interface CurrentWeatherResponse {
  lightning?: {
    data: Array<{
      place: string;
      occur: "true" | "false";
    }>;
    startTime: string;
    endTime: string;
  };

  rainfall?: {
    data: Array<{
      unit: "mm";
      place: string;
      max: number;
      min?: number;
      main: "TRUE" | "FALSE";
    }>;
    startTime: string;
    endTime: string;
  };

  icon: number[];
  iconUpdateTime?: string;

  uvindex?: {
    data: Array<{
      place: string;
      value: number;
      desc?: string;
    }>;
    recordDesc?: string;
  };

  temperature?: {
    data: Array<{
      place: string;
      value: number;
      unit: "C";
    }>;
    recordTime: string;
  };

  humidity?: {
    data: Array<{
      place: string;
      value: number;
      unit: "percent";
    }>;
    recordTime: string;
  };

  updateTime: string;

  warningMessage?: string | string[];
  rainstormReminder?: string | string[];
  specialWxTips?: string[];
  tcmessage?: string | string[];
  mintempFrom00To09?: string;
  rainfallFrom00To12?: string;
  rainfallLastMonth?: string;
  rainfallJanuaryToLastMonth?: string;
}
```

Example fragment:

```json
{
  "icon": [62],
  "temperature": {
    "data": [
      {"place": "Hong Kong Observatory", "value": 26, "unit": "C"}
    ],
    "recordTime": "2026-07-16T16:00:00+08:00"
  },
  "humidity": {
    "recordTime": "2026-07-16T16:00:00+08:00",
    "data": [
      {"unit": "percent", "value": 93, "place": "Hong Kong Observatory"}
    ]
  },
  "updateTime": "2026-07-16T16:02:00+08:00"
}
```

The `rhrread` rainfall object is district-level bulletin data and is not identical to the automatic-weather-station dataset in section 4.

## 7. Local weather forecast

### 7.1 Calling method

```http
GET https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=flw&lang=en
```

This is HKO's regular human-authored forecast for Hong Kong. It answers what weather is expected, independently of whether official warnings are active.

### 7.2 Return format

```ts
interface LocalWeatherForecast {
  generalSituation: string;
  tcInfo: string;
  fireDangerWarning: string;
  forecastPeriod: string;
  forecastDesc: string;
  outlook: string;
  updateTime: string;
}
```

Example:

```json
{
  "generalSituation": "A trough of low pressure is affecting Guangdong...",
  "tcInfo": "",
  "fireDangerWarning": "",
  "forecastPeriod": "Weather forecast for this afternoon and tonight",
  "forecastDesc": "Mainly cloudy with occasional showers...",
  "outlook": "Showers will remain heavy at times tomorrow...",
  "updateTime": "2026-07-16T14:45:00+08:00"
}
```

## 8. 9-day weather forecast

### 8.1 Calling method

```http
GET https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=fnd&lang=en
```

The forecast is normally issued twice daily and whenever it is updated. It contains nine daily forecasts plus the general situation, update time, sea temperature and soil-temperature observations.

Parameters:

| Parameter | Required | Values | Meaning |
|---|---:|---|---|
| `dataType` | Yes | `fnd` | 9-day forecast |
| `lang` | No | `en`, `tc`, `sc` | Response language; default `en` |

### 8.2 Return format

```ts
interface NineDayForecastResponse {
  generalSituation: string;
  weatherForecast: Array<{
    forecastDate: string;       // YYYYMMDD
    week: string;
    forecastWind: string;
    forecastWeather: string;
    forecastMaxtemp: ValueUnit<"C">;
    forecastMintemp: ValueUnit<"C">;
    forecastMaxrh: ValueUnit<"percent">;
    forecastMinrh: ValueUnit<"percent">;
    ForecastIcon: number;
    PSR: "High" | "Medium High" | "Medium" | "Medium Low" | "Low";
  }>;
  updateTime: string;
  seaTemp?: {
    place: string;
    value: number;
    unit: "C";
    recordTime: string;
  };
  soilTemp?: Array<{
    place: string;
    value: number;
    unit: "C";
    recordTime: string;
    depth: {
      unit: "metre";
      value: number;
    };
  }>;
}

interface ValueUnit<Unit extends string> {
  value: number;
  unit: Unit;
}
```

Example fragment:

```json
{
  "generalSituation": "The weather over the coast of Guangdong will remain unsettled...",
  "weatherForecast": [
    {
      "forecastDate": "20260717",
      "week": "Friday",
      "forecastWind": "South to southwest force 4.",
      "forecastWeather": "Mainly cloudy with occasional showers.",
      "forecastMaxtemp": {"value": 30, "unit": "C"},
      "forecastMintemp": {"value": 26, "unit": "C"},
      "forecastMaxrh": {"value": 95, "unit": "percent"},
      "forecastMinrh": {"value": 75, "unit": "percent"},
      "ForecastIcon": 63,
      "PSR": "High"
    }
  ],
  "updateTime": "2026-07-16T11:30:00+08:00"
}
```

`PSR` means Probability of Significant Rain. `ForecastIcon` is intentionally capitalized in HKO's JSON and should be accessed with that exact spelling.

## 9. Weather warning information

### 9.1 Calling method

```http
GET https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=warningInfo&lang=en
```

This endpoint returns the detailed human-readable warning bulletins and safety information. Use it for the contents of a warning-detail screen.

### 9.2 Return format

```ts
interface WarningInformation {
  details: Array<{
    contents: string[];
    warningStatementCode: WarningStatementCode;
    subtype?: string;
    updateTime: string;
  }>;
}

type WarningStatementCode =
  | "WFIRE"
  | "WFROST"
  | "WHOT"
  | "WCOLD"
  | "WMSGNL"
  | "WTCPRE8"
  | "WRAIN"
  | "WFNTSA"
  | "WL"
  | "WTCSGNL"
  | "WTMW"
  | "WTS";
```

Example:

```json
{
  "details": [
    {
      "contents": [
        "Thunderstorm Warning has been issued...",
        "Members of the public are advised to take precautions..."
      ],
      "warningStatementCode": "WTS",
      "updateTime": "2026-07-16T14:00:00+08:00"
    }
  ]
}
```

`subtype` is mainly used for fire-danger, rainstorm and tropical-cyclone warnings.

## 10. Weather warning summary

### 10.1 Calling method

```http
GET https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=warnsum&lang=en
```

This endpoint is a compact machine-readable snapshot suitable for warning badges, notification logic and active-warning lists.

### 10.2 Return format

The top-level property names are dynamic warning categories:

```ts
type WarningSummary = Record<
  string,
  {
    name: string;
    code: string;
    type?: string;
    actionCode: "ISSUE" | "REISSUE" | "CANCEL" | "EXTEND" | "UPDATE";
    issueTime?: string;
    expireTime?: string;
    updateTime: string;
  }
>;
```

Example:

```json
{
  "WTS": {
    "name": "Thunderstorm Warning",
    "code": "WTS",
    "actionCode": "EXTEND",
    "issueTime": "2026-07-16T05:19:00+08:00",
    "expireTime": "2026-07-16T16:30:00+08:00",
    "updateTime": "2026-07-16T14:00:00+08:00"
  }
}
```

An empty object means there is no warning summary to display:

```json
{}
```

Do not assume the top-level `code` and the category property name are identical. For example, the `WRAIN` category may contain a `code` such as `WRAINA`, `WRAINR` or `WRAINB`.

## 11. Special weather tips

### 11.1 Calling method

```http
GET https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=swt&lang=en
```

Special weather tips are flexible advisories that do not necessarily correspond to an official warning signal. They can include localised heavy rain, advance warning of a possible signal, unusual developments or public arrangements.

### 11.2 Return format

```ts
interface SpecialWeatherTips {
  swt: Array<{
    desc: string;
    updateTime: string;
  }>;
}
```

Example:

```json
{
  "swt": [
    {
      "desc": "Announcement on Localised Heavy Rain...",
      "updateTime": "2026-07-16T14:10:00+08:00"
    }
  ]
}
```

When there are no active tips:

```json
{"swt": []}
```

## 12. Smart-lamppost meteorological data

### 12.1 Supporting lookup datasets

Before calling the observation endpoint, retrieve the location, device-type and element databases:

```text
https://www.hko.gov.hk/common/hko_data/smart-lamppost/files/smart_lamppost_met_device_location.json
https://www.hko.gov.hk/common/hko_data/smart-lamppost/files/smart_lamppost_met_device_type.json
https://www.hko.gov.hk/common/hko_data/smart-lamppost/files/smart_lamppost_met_device_element.json
```

Use the location database to obtain `LP_NUM` and the type/element databases to determine which device IDs and elements are available.

### 12.2 Calling method

```http
GET https://data.weather.gov.hk/weatherAPI/smart-lamppost/smart-lamppost.php?pi=GF3637&di=01
```

Parameters:

| Parameter | Required | Meaning |
|---|---:|---|
| `pi` | Yes | Lamppost ID, maximum 8 characters |
| `di` | Yes | Meteorological device ID, 2 characters |

The response contains the latest processed 10-minute observation for one lamppost/device pair.

### 12.3 Return format

```ts
interface SmartLamppostResponse {
  BD: string;
  DI: string;
  GI: string;
  PI: string;
  TS: string;
  BODY: {
    HKO: {
      VN: string;  // payload version
      T0?: string; // air temperature, degrees Celsius
      RH?: string; // relative humidity, percent
      WS?: string; // 10-minute mean wind speed, km/h
      WD?: string; // 10-minute mean direction, degrees
      DH?: string; // device height, metres
      TS: string;  // measurement time, YYYYMMDDHHmmss
      TP: string;  // processed time, YYYYMMDDHHmmss
    };
  };
}
```

Example:

```json
{
  "BD": "00",
  "DI": "01",
  "GI": "00",
  "PI": "GF3637",
  "TS": "0",
  "BODY": {
    "HKO": {
      "RH": "71.7",
      "T0": "33.5",
      "TS": "20230913174049",
      "VN": "1.0",
      "WS": "4",
      "WD": "143",
      "DH": "12",
      "TP": "20230913174049"
    }
  }
}
```

Error examples:

```json
{"message": "No record found"}
```

```json
{"message": "Missing required request parameters: [di, pi]"}
```

All measurement values are strings. `////` indicates that the corresponding element failed quality control.

## 13. Regional weather products

### 13.1 Latest 1-minute mean air temperature

Calling method:

```http
GET https://data.weather.gov.hk/weatherAPI/hko_data/regional-weather/latest_1min_temperature.csv
```

Return format:

```csv
Date time,Automatic Weather Station,Air Temperature(degree Celsius)
202607161600,Chek Lap Kok,27.3
202607161600,Cheung Chau,N/A
202607161600,Clear Water Bay,25.4
```

```ts
interface LatestTemperatureRow {
  dateTime: string;                // YYYYMMDDHHmm
  automaticWeatherStation: string;
  airTemperature: string;          // decimal or N/A
}
```

This regional product contains provisional data and is normally refreshed every 10 minutes.

### 13.2 Latest 10-minute mean wind direction, speed and maximum gust

Calling method:

```http
GET https://data.weather.gov.hk/weatherAPI/hko_data/regional-weather/latest_10min_wind.csv
```

The CSV contains the latest 10-minute mean wind direction, mean wind speed and maximum gust for each reporting automatic weather station. It is provisional and normally updated every 10 minutes.

Return format:

```csv
Date time,Automatic Weather Station,10-Minute Mean Wind Direction(Compass points),10-Minute Mean Speed(km/hour),10-Minute Maximum Gust(km/hour)
202607141430,Central Pier,South,10,30
202607141430,Cheung Chau,Southwest,36,47
202607141430,Wong Chuk Hang,Variable,4,12
```

Logical row type:

```ts
interface LatestWindRow {
  dateTime: string;                   // YYYYMMDDHHmm, Hong Kong time
  automaticWeatherStation: string;
  meanWindDirection: string;          // compass point, Calm, Variable or N/A
  meanWindSpeed: string;              // km/h, blank when calm, or N/A
  maximumGust: string;                // km/h or N/A
}
```

Parsing rules:

- direction is a compass-point string such as `North`, `Southeast` or `Southwest`, not an angle in degrees;
- `Calm` indicates calm wind;
- `Variable` indicates variable wind direction;
- mean speed is blank for calm wind;
- unavailable values are represented by `N/A`;
- speed and gust should only be converted to numbers after checking for blank and `N/A` values.

## 14. HKO Earth Weather prediction models

Viewer: <https://maps.weather.gov.hk/wxviewer/index.html?lang=en>

### 14.1 Important status warning

The paths in this section were inferred from the current HKO Earth Weather web application. They are **not described by HKO as a versioned public API**.

Consequences:

- filenames, model IDs, field codes and encoding can change without notice;
- availability is not guaranteed;
- historical files may be removed;
- browser CORS or hotlink controls may change;
- the data licence can differ by model;
- the raster files are not a substitute for documented raw numerical model data.

Use these feeds experimentally or behind a monitored server-side adapter. For ECMWF and AIFS numerical data in production, prefer ECMWF's official open-data service.

### 14.2 Models and official displayed products

| Viewer label | Internal ID | Displayed surface products | Forecast interval and range |
|---|---|---|---|
| ECMWF | `ec` | wind, gust, temperature, RH, MSL pressure, rainfall and potential-thunderstorm product | 3-hourly through hour 144, then 6-hourly through hour 360 |
| ECMWF-AIFS | `aifs` | wind, temperature, RH, MSL pressure and rainfall | 6-hourly through hour 360 |
| Fengwu | `fengwu_ec` | wind, temperature, MSL pressure and rainfall | 6-hourly through hour 360 |
| Fuxi | `fuxi_ec` | wind, temperature, RH, MSL pressure and rainfall | 6-hourly through hour 360 |
| Pangu | `pangu_ec` | wind, temperature and MSL pressure | 6-hourly through hour 360 |
| AAMC-WRF | `aamc` | wind, temperature, RH, MSL pressure and rainfall | 3-hourly through hour 120 |

The viewer also presents upper-air products where supported at pressure levels `200`, `500`, `700`, `850` and `925` hPa. Surface level is represented by `sfc`.

HKO states that these are direct computer-model products without manual adjustment. They can differ from HKO's official local forecast and official tropical-cyclone forecast track.

### 14.3 Discovering the latest base time

Each model has a small current-cycle JSON resource:

```text
https://maps.weather.gov.hk/wxviewer/data/current_ec.json
https://maps.weather.gov.hk/wxviewer/data/current_aifs.json
https://maps.weather.gov.hk/wxviewer/data/current_fengwu_ec.json
https://maps.weather.gov.hk/wxviewer/data/current_fuxi_ec.json
https://maps.weather.gov.hk/wxviewer/data/current_pangu_ec.json
https://maps.weather.gov.hk/wxviewer/data/current_aamc.json
```

Typical response:

```json
{
  "default": "2026071512",
  "tc_track": null
}
```

Some responses include product-specific base cycles:

```json
{
  "default": "2026071512",
  "tc_track": null,
  "WH": "2026071500",
  "SH": "2026071500",
  "WP": "2026071500",
  "WD": "2026071500",
  "SD": "2026071500",
  "SC": "2026071500"
}
```

Use `default` for atmospheric products. The other keys are used for wave, swell and sea-state layers.

JavaScript:

```js
const model = "aifs";

const current = await getJson(
  `https://maps.weather.gov.hk/wxviewer/data/current_${model}.json`
);

const baseTime = current.default;
```

### 14.4 Raster layer URL format

The atmospheric raster pattern is:

```text
https://maps.weather.gov.hk/wxviewer/data/weather/
{model}/{baseTime}/
{model}_{baseTime}_{validTime}_f{lead}_{level}_{field}.png
```

All parts are concatenated into one URL. For example:

```text
https://maps.weather.gov.hk/wxviewer/data/weather/ec/2026071512/ec_2026071512_2026071512_f000_sfc_TT.png
```

Components:

| Component | Format | Example |
|---|---|---|
| `model` | Internal ID | `ec`, `aifs`, `fuxi_ec` |
| `baseTime` | UTC `YYYYMMDDHH` | `2026071512` |
| `validTime` | UTC `YYYYMMDDHH` | `2026071600` |
| `lead` | zero-padded forecast hour | `000`, `012`, `144`, `150` |
| `level` | `sfc` or pressure level | `sfc`, `850`, `200` |
| `field` | viewer field code | `TT`, `WS`, `RF` |

The relationship between the times must be:

```text
validTime = baseTime + lead hours
```

Useful field codes found in the viewer:

| Code | Meaning | Usual unit after decoding |
|---|---|---|
| `TT` | air temperature | Kelvin internally; viewer displays °C/°F/K |
| `WS` | wind speed colour field | m/s internally |
| `UV` | horizontal wind vector components | m/s |
| `GST` | wind gust | m/s |
| `RF` | rainfall | mm |
| `RH` | relative humidity | % |
| `DV` | divergence | s⁻¹-scaled viewer value |
| `VO` | vorticity | s⁻¹-scaled viewer value |

Do not assume every model produces every field. Use the availability table in section 14.2 and handle HTTP 404 or image-load failure.

### 14.5 Raster return format

The return type is an RGBA PNG, typically representing the whole model domain on a fixed grid. It is not a JSON array and should not be interpreted as a pre-coloured screenshot.

The viewer uses its JavaScript rendering layer to:

1. map image pixels to the model domain;
2. decode model values from pixel channels;
3. apply product-specific gradients;
4. draw scalar shading or animated vector particles.

HKO does not publish a stable schema describing the raster channel encoding, grid geometry and missing-value handling. Therefore:

- the PNG can be displayed using the current viewer logic;
- extracting authoritative values at arbitrary coordinates requires reverse-engineering and continuously testing the viewer's decoder;
- for raw values, use the original model provider's documented numerical data instead.

### 14.6 Pressure and geopotential contours

The viewer loads contour data as KML using this pattern:

```text
https://maps.weather.gov.hk/wxviewer/data/weather/
{model}/{baseTime}/
{model}_{baseTime}_{validTime}_f{lead}_{level}_{contour}.kml
```

`contour` is normally:

- `MSL` at `sfc` for mean sea-level pressure;
- `GPH` at a pressure level for geopotential height.

KML responses contain geographic contour lines and labels. Treat the exact feature properties as internal viewer implementation details.

### 14.7 ECMWF thunderstorm overlay

The ECMWF viewer can load its potential-thunderstorm overlay as a PNG with a `TS` suffix:

```text
.../data/weather/ec/{baseTime}/ec_{baseTime}_{validTime}_f{lead}_sfc_TS.png
```

This is an HKO post-processed display product, not a general HKO warning and not the same thing as an official Thunderstorm Warning (`WTS`).

### 14.8 Building a model raster URL

```js
function parseModelTime(value) {
  const year = Number(value.slice(0, 4));
  const month = Number(value.slice(4, 6)) - 1;
  const day = Number(value.slice(6, 8));
  const hour = Number(value.slice(8, 10));
  return new Date(Date.UTC(year, month, day, hour));
}

function formatModelTime(date) {
  const pad = value => String(value).padStart(2, "0");
  return (
    date.getUTCFullYear() +
    pad(date.getUTCMonth() + 1) +
    pad(date.getUTCDate()) +
    pad(date.getUTCHours())
  );
}

async function buildModelRasterUrl({
  model,
  leadHour,
  level = "sfc",
  field = "TT",
}) {
  const root = "https://maps.weather.gov.hk/wxviewer";
  const current = await getJson(`${root}/data/current_${model}.json`);
  const baseTime = current.default;

  const validDate = parseModelTime(baseTime);
  validDate.setUTCHours(validDate.getUTCHours() + leadHour);

  const validTime = formatModelTime(validDate);
  const lead = String(leadHour).padStart(3, "0");
  const filename =
    `${model}_${baseTime}_${validTime}_f${lead}_${level}_${field}.png`;

  return `${root}/data/weather/${model}/${baseTime}/${filename}`;
}

const url = await buildModelRasterUrl({
  model: "aifs",
  leadHour: 24,
  field: "TT",
});

console.log(url);
```

This code only constructs the URL. It does not decode the PNG into numerical forecast values.

### 14.9 Automatic city forecast feed

Earth Weather also loads an auxiliary machine-readable city forecast, but it is not exposed as a selectable per-model comparison.

First retrieve the current version token:

```http
GET https://maps.weather.gov.hk/wxviewer/data/city_forecast/current.txt
```

Then request:

```text
https://maps.weather.gov.hk/wxviewer/data/city_forecast/{token}.json
```

Example code:

```js
const root = "https://maps.weather.gov.hk/wxviewer/data/city_forecast";

const tokenResponse = await fetch(`${root}/current.txt`);
if (!tokenResponse.ok) throw new Error(`Token request failed: ${tokenResponse.status}`);

const token = (await tokenResponse.text()).trim();
const cityForecast = await getJson(`${root}/${token}.json`);
```

Typical structure:

```ts
interface CityForecastResponse {
  result: Array<{
    stationId: number;
    stationOfficialId: string;
    stationName: string;
    lat: number;
    lon: number;
    height: number;
    heightUnit: string;
    timezone: number;
    ocfs: Array<{
      cycle: number;
      forecastHour: number;
      temperature: number;
      temperatureUnit: string;
      relativeHumidity: number;
      relativeHumidityUnit: string;
      windSpeed: number;
      windSpeedUnit: string;
      windDirection: number;
      windDirectionUnit: string;
      totalCloudCover?: number;
      totalCloudCoverUnit?: string;
      pressure?: number;
      pressureUnit?: string;
      visibility?: number;
      visibilityUnit?: string;
      dateTimeUtc: number;
      dateTimeLocal: number;
      weatherIcon?: number;
      weatherIconWWIS?: string;
    }>;
  }>;
}
```

This JSON can be several megabytes. Cache the token and response rather than downloading it separately for every user request.

## 15. Automatic Regional Weather Forecast (OCF) internal feeds

Viewer: <https://maps.weather.gov.hk/ocf/>

Official product notes: <https://maps.weather.gov.hk/ocf/help_e.html>

### 15.1 Interface status and common behaviour

The OCF site describes the forecast products, but it does not publish the website's data-file paths as a versioned public API. The calling methods in this section were inferred from the current OCF application and verified against live responses.

Consequences:

- paths, station codes, filenames and schemas can change without notice;
- a filename ending in `.xml` currently contains JSON, not XML;
- no stable station-discovery endpoint is documented;
- missing forecast values may be omitted or represented by `M`;
- a maintenance response can replace the normal forecast structure;
- use a monitored server-side adapter and validate every response before storing it.

The OCF nine-day station forecasts are automatic multi-model consensus products. HKO corrects contributing model forecasts using observations and combines them with weights based on past performance. They are not manually adjusted official forecasts.

### 15.2 Nine-day station forecast

#### 15.2.1 Meaning and update schedule

For supported Hong Kong stations, OCF supplies an hourly forecast for the next nine days containing air temperature, relative humidity, wind direction and wind speed. It also provides three-hourly weather-icon codes and daily summaries containing minimum and maximum temperature, a weather-icon code and probability of precipitation.

The hourly temperature is specific to the selected station. This is more spatially and temporally detailed than the documented `fnd` forecast, which provides daily minimum and maximum temperatures for Hong Kong generally.

The daily probability of precipitation is the chance that at least `0.5 mm` of rain will occur near the selected station. The possible values are:

```text
<10%, 20%, 40%, 60%, 80%, >90%
```

This is not the same field as `PSR` in the documented nine-day forecast. OCF probability of precipitation is station-specific and concerns the occurrence of at least 0.5 mm of rain; `PSR` is HKO's qualitative Probability of Significant Rain for the general Hong Kong forecast.

The station forecasts normally update around noon and midnight.

#### 15.2.2 Calling method

```http
GET https://maps.weather.gov.hk/ocf/dat/{stationCode}.xml
```

Example using the current station code `CCH`:

```http
GET https://maps.weather.gov.hk/ocf/dat/CCH.xml
```

Treat the response as JSON even though the path ends in `.xml`:

```js
const response = await fetch("https://maps.weather.gov.hk/ocf/dat/CCH.xml");
if (!response.ok) throw new Error(`OCF request failed: ${response.status}`);

const forecast = await response.json();
const dailyForecast = forecast.DailyForecast.map(day => ({
  date: day.ForecastDate,
  minimumTemperatureC: day.ForecastMinimumTemperature,
  maximumTemperatureC: day.ForecastMaximumTemperature,
  precipitationProbability: day.ForecastChanceOfRain,
}));
const hourlyTemperature = forecast.HourlyWeatherForecast.map(hour => ({
  forecastHour: hour.ForecastHour,
  temperatureC: hour.ForecastTemperature,
}));
```

Station codes are internal OCF identifiers. Obtain the required code from a successfully selected location in the current OCF application and keep the mapping configurable rather than assuming it is permanent.

#### 15.2.3 Return format

The station response contains both hourly and daily forecast fields:

```ts
interface OcfStationForecast {
  LastModified: number | string; // YYYYMMDDHHmmss
  StationCode: string;
  Latitude: number;
  Longitude: number;
  ModelTime: number | string;    // YYYYMMDDHH
  DailyForecast: Array<{
    ForecastDate: string;                 // YYYYMMDD
    ForecastChanceOfRain:                 // probability of >= 0.5 mm
      "<10%" | "20%" | "40%" | "60%" | "80%" | ">90%" | "M";
    ForecastDailyWeather?: number | "M"; // OCF weather-icon code
    ForecastMaximumTemperature?: number | "M"; // degrees Celsius
    ForecastMinimumTemperature?: number | "M"; // degrees Celsius
  }>;
  HourlyWeatherForecast?: Array<{
    ForecastHour: string;                 // YYYYMMDDHH
    ForecastRelativeHumidity?: number | "M"; // percent
    ForecastTemperature?: number | "M";      // degrees Celsius
    ForecastWeather?: number | "M";          // normally at 3-hour intervals
    ForecastWindDirection?: number | "M";    // degrees
    ForecastWindSpeed?: number | "M";        // kilometres per hour
  }>;
}
```

Example fragment:

```json
{
  "StationCode": "CCH",
  "Latitude": 22.201,
  "Longitude": 114.027,
  "ModelTime": 2026071512,
  "DailyForecast": [
    {
      "ForecastDate": "20260716",
      "ForecastChanceOfRain": "80%",
      "ForecastDailyWeather": 63,
      "ForecastMaximumTemperature": 27.2,
      "ForecastMinimumTemperature": 24.8
    }
  ],
  "HourlyWeatherForecast": [
    {
      "ForecastHour": "2026071611",
      "ForecastRelativeHumidity": 92.0,
      "ForecastTemperature": 25.6,
      "ForecastWindDirection": 258.0,
      "ForecastWindSpeed": 15.5
    }
  ]
}
```

Store `ForecastChanceOfRain` as a category. Do not convert `<10%` to zero or `>90%` to 100 without retaining the original value. Treat `ForecastHour` as Hong Kong local time in `YYYYMMDDHH` format and do not interpret it as UTC.

## 16. Recommended application mapping

| Application feature | Preferred feed |
|---|---|
| Current station temperature/humidity | Current weather report or regional temperature CSV |
| Station rainfall during the last hour | `hourlyRainfall.php` |
| District rainfall bulletin | `rhrread` rainfall property |
| Short-range rainfall map | Gridded rainfall nowcast CSV |
| Regular Hong Kong forecast | Local weather forecast (`flw`) |
| Daily forecast for the next nine days | 9-day weather forecast (`fnd`) |
| Latest station wind and gust | Regional 10-minute wind CSV |
| Warning badges/notification state | Warning summary (`warnsum`) |
| Full warning text and safety instructions | Warning information (`warningInfo`) |
| Advisory banner | Special weather tips (`swt`) |
| Experimental hyperlocal observations | Smart-lamppost API |
| Nine-day station temperature and daily chance of rain | OCF nine-day station forecast, with internal-interface warning |
| Model map comparison | Earth Weather raster assets, with internal-interface warning |
| Raw ECMWF/AIFS numerical modelling | ECMWF official open data rather than HKO viewer PNGs |

## 17. Implementation recommendations

1. **Call HKO from a server-side adapter where possible.** This permits caching, schema validation, timeouts and resilience if browser CORS rules change.
2. **Cache according to the update interval.** Do not request a 10-minute feed every few seconds.
3. **Store the source observation/forecast time.** The HTTP retrieval time is not the data time.
4. **Treat numbers defensively.** Handle `M`, `N/A`, `////`, empty strings and omitted properties.
5. **Preserve the original text for warnings and forecasts.** Do not derive safety-critical meaning solely from keyword matching.
6. **Use warning summary and warning information together.** The summary drives state and badges; warning information supplies the detailed bulletin.
7. **Monitor undocumented viewer integrations.** Add response-content checks so an HTML error page is not accepted as a PNG, KML, JSON or OCF `.xml` response.
8. **Review data terms and attribution.** Model-provider licences differ, particularly when redistributing model output.

## 18. Sources

- HKO Open Data catalogue: <https://www.hko.gov.hk/en/abouthko/opendata_intro.htm>
- HKO Open Data API documentation: <https://data.weather.gov.hk/weatherAPI/doc/HKO_Open_Data_API_Documentation.pdf>
- Gridded rainfall nowcast format: <https://data.weather.gov.hk/weatherAPI/hko_data/F3/HKO_gridded_rainfall_nowcast_documentation.pdf>
- Regional 1-minute temperature format: <https://data.weather.gov.hk/weatherAPI/hko_data/regional-weather/HKO_open_data_temperature_Documentation.pdf>
- Regional 10-minute wind format: <https://data.weather.gov.hk/weatherAPI/hko_data/regional-weather/HKO_open_data_10min_wind_Documentation.pdf>
- Smart-lamppost data dictionary: <https://www.hko.gov.hk/common/hko_data/smart-lamppost/files/smart_lamppost_data_spec.pdf>
- HKO Earth Weather viewer: <https://maps.weather.gov.hk/wxviewer/index.html?lang=en>
- HKO Earth Weather notes: <https://maps.weather.gov.hk/wxviewer/notes.html>
- HKO Automatic Regional Weather Forecast viewer: <https://maps.weather.gov.hk/ocf/>
- HKO Automatic Regional Weather Forecast product notes: <https://maps.weather.gov.hk/ocf/help_e.html>
- ECMWF open-data documentation: <https://confluence.ecmwf.int/spaces/DAC/pages/272310539/ECMWF+open+data%3A+real-time+forecasts+from+IFS+and+AIFS>
