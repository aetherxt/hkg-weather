import type {
  AstronomicalTimes,
  CurrentWeather,
  DashboardSnapshot,
  DataResponse,
  LamppostReading,
  ListResponse,
  LocalForecast,
  NineDayForecast,
  ResponseMetadata,
  StationRainfallResponse,
  TemperatureReading,
  Warnings,
  WeatherErrorDetail,
  WindReading,
} from "./types.ts";

export type WeatherApiErrorStatus = 404 | 422 | 503;
export type WeatherApiErrorKind =
  | "not-found"
  | "invalid-request"
  | "unavailable";

export type WeatherFetch = (
  input: RequestInfo | URL,
  init?: RequestInit,
) => Promise<Response>;

export interface WeatherClientOptions {
  baseUrl?: string;
  fetch?: WeatherFetch;
  requestInit?: RequestInit;
}

const ERROR_KINDS: Record<WeatherApiErrorStatus, WeatherApiErrorKind> = {
  404: "not-found",
  422: "invalid-request",
  503: "unavailable",
};

export class WeatherApiError extends Error {
  readonly status: WeatherApiErrorStatus;
  readonly kind: WeatherApiErrorKind;
  readonly detail: WeatherErrorDetail;
  readonly endpoint: string;

  constructor(
    status: WeatherApiErrorStatus,
    detail: WeatherErrorDetail,
    endpoint: string,
  ) {
    const message =
      typeof detail === "string"
        ? detail
        : detail.map((issue) => issue.msg ?? "Invalid request").join("; ");
    super(message || `Weather API request failed with status ${status}`);
    this.name = "WeatherApiError";
    this.status = status;
    this.kind = ERROR_KINDS[status];
    this.detail = detail;
    this.endpoint = endpoint;
  }
}

export class WeatherResponseDecodeError extends Error {
  readonly endpoint: string;

  constructor(endpoint: string, message: string) {
    super(message);
    this.name = "WeatherResponseDecodeError";
    this.endpoint = endpoint;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isApiErrorStatus(status: number): status is WeatherApiErrorStatus {
  return status === 404 || status === 422 || status === 503;
}

function isErrorDetail(value: unknown): value is WeatherErrorDetail {
  return (
    typeof value === "string" ||
    (Array.isArray(value) && value.every((issue) => isRecord(issue)))
  );
}

function assertNullableDateTime(
  value: unknown,
  field: string,
  endpoint: string,
): asserts value is string | null {
  if (value !== null && typeof value !== "string") {
    throw new WeatherResponseDecodeError(
      endpoint,
      `Weather API response has an invalid ${field}`,
    );
  }
}

function decodeMetadata(value: unknown, endpoint: string): ResponseMetadata {
  if (!isRecord(value) || typeof value.dataset !== "string") {
    throw new WeatherResponseDecodeError(
      endpoint,
      "Weather API response has invalid metadata",
    );
  }
  assertNullableDateTime(value.sourceUpdatedAt, "sourceUpdatedAt", endpoint);
  assertNullableDateTime(value.fetchedAt, "fetchedAt", endpoint);
  return {
    dataset: value.dataset,
    sourceUpdatedAt: value.sourceUpdatedAt,
    fetchedAt: value.fetchedAt,
  };
}

async function decodeJson(response: Response, endpoint: string): Promise<unknown> {
  const body = await response.text();
  try {
    return JSON.parse(body) as unknown;
  } catch {
    throw new WeatherResponseDecodeError(
      endpoint,
      "Weather API returned a non-JSON response",
    );
  }
}

function errorDetail(payload: unknown, statusText: string): WeatherErrorDetail {
  if (isRecord(payload) && isErrorDetail(payload.detail)) {
    return payload.detail;
  }
  return statusText || "Weather API request failed";
}

function mergeRequestInit(
  defaults: RequestInit | undefined,
  overrides: RequestInit | undefined,
): RequestInit {
  const headers = new Headers(defaults?.headers);
  new Headers(overrides?.headers).forEach((value, key) => headers.set(key, value));
  if (!headers.has("accept")) {
    headers.set("accept", "application/json");
  }
  return {
    ...defaults,
    ...overrides,
    body: undefined,
    headers,
    method: "GET",
  };
}

function endpointUrl(path: string, baseUrl: string): string {
  const endpoint = `/api/weather${path}`;
  return baseUrl ? new URL(endpoint, baseUrl).toString() : endpoint;
}

async function requestEnvelope<Data>(
  endpoint: string,
  fetcher: WeatherFetch,
  init: RequestInit,
  list: false,
): Promise<DataResponse<Data>>;
async function requestEnvelope<Item>(
  endpoint: string,
  fetcher: WeatherFetch,
  init: RequestInit,
  list: true,
): Promise<ListResponse<Item>>;
async function requestEnvelope<Data>(
  endpoint: string,
  fetcher: WeatherFetch,
  init: RequestInit,
  list: boolean,
): Promise<DataResponse<Data> | ListResponse<Data>> {
  const response = await fetcher(endpoint, init);
  const payload = await decodeJson(response, endpoint);

  if (!response.ok) {
    if (isApiErrorStatus(response.status)) {
      throw new WeatherApiError(
        response.status,
        errorDetail(payload, response.statusText),
        endpoint,
      );
    }
    throw new WeatherResponseDecodeError(
      endpoint,
      `Unexpected weather API status ${response.status}`,
    );
  }

  if (!isRecord(payload) || !("data" in payload)) {
    throw new WeatherResponseDecodeError(
      endpoint,
      "Weather API response has an invalid envelope",
    );
  }
  const meta = decodeMetadata(payload.meta, endpoint);
  if (list) {
    if (!Array.isArray(payload.data)) {
      throw new WeatherResponseDecodeError(
        endpoint,
        "Weather API list response has invalid data",
      );
    }
    const rawMeta = payload.meta;
    if (!isRecord(rawMeta) || typeof rawMeta.count !== "number") {
      throw new WeatherResponseDecodeError(
        endpoint,
        "Weather API list response has an invalid count",
      );
    }
    return {
      data: payload.data as Data[],
      meta: { ...meta, count: rawMeta.count },
    };
  }
  return { data: payload.data as Data, meta };
}

export function createWeatherClient(options: WeatherClientOptions = {}) {
  const baseUrl = options.baseUrl?.replace(/\/$/, "") ?? "";
  const fetcher = options.fetch ?? globalThis.fetch.bind(globalThis);

  function data<Data>(path: string, init?: RequestInit) {
    const endpoint = endpointUrl(path, baseUrl);
    return requestEnvelope<Data>(
      endpoint,
      fetcher,
      mergeRequestInit(options.requestInit, init),
      false,
    );
  }

  function list<Item>(path: string, init?: RequestInit) {
    const endpoint = endpointUrl(path, baseUrl);
    return requestEnvelope<Item>(
      endpoint,
      fetcher,
      mergeRequestInit(options.requestInit, init),
      true,
    );
  }

  return {
    getDashboard: (init?: RequestInit) =>
      data<DashboardSnapshot>("/dashboard", init),
    getWarnings: (init?: RequestInit) => data<Warnings>("/warnings", init),
    getCurrentWeather: (init?: RequestInit) =>
      data<CurrentWeather>("/current", init),
    getLocalForecast: (init?: RequestInit) =>
      data<LocalForecast>("/forecast/local", init),
    getNineDayForecast: (init?: RequestInit) =>
      data<NineDayForecast>("/forecast/nine-day", init),
    getRegionalTemperature: (init?: RequestInit) =>
      list<TemperatureReading>("/regional/temperature", init),
    getRegionalWind: (init?: RequestInit) =>
      list<WindReading>("/regional/wind", init),
    getLampposts: (init?: RequestInit) =>
      list<LamppostReading>("/lampposts", init),
    getAstronomicalTimes: (init?: RequestInit) =>
      data<AstronomicalTimes>("/sun", init),
    getStationRainfall: (init?: RequestInit) =>
      data<StationRainfallResponse>("/rainfall/stations", init),
  };
}

export type WeatherClient = ReturnType<typeof createWeatherClient>;

export const weatherClient = createWeatherClient();
