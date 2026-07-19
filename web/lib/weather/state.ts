import {
  WeatherApiError,
  type WeatherApiErrorKind,
  type WeatherApiErrorStatus,
} from "./client.ts";
import type { DataResponse, ResponseMetadata } from "./types.ts";

export interface WeatherSectionError {
  kind: WeatherApiErrorKind | "unexpected";
  message: string;
  status: WeatherApiErrorStatus | null;
}

export interface LoadingWeatherSection {
  status: "loading";
}

export interface LoadedWeatherSection<Data> {
  data: Data;
  meta: ResponseMetadata;
  sourceUpdatedAt: string | null;
  fetchedAt: string | null;
}

export interface ReadyWeatherSection<Data>
  extends LoadedWeatherSection<Data> {
  status: "ready";
}

export interface StaleWeatherSection<Data>
  extends LoadedWeatherSection<Data> {
  status: "stale";
}

export interface UnavailableWeatherSection {
  status: "unavailable";
  error: WeatherSectionError;
  canRetry: boolean;
}

export interface RetryingWeatherSection<Data> {
  status: "retrying";
  previous?: ReadyWeatherSection<Data> | StaleWeatherSection<Data>;
}

export type WeatherSectionState<Data> =
  | LoadingWeatherSection
  | ReadyWeatherSection<Data>
  | StaleWeatherSection<Data>
  | UnavailableWeatherSection
  | RetryingWeatherSection<Data>;

export function loadingWeatherSection(): LoadingWeatherSection {
  return { status: "loading" };
}

export function retryingWeatherSection<Data>(
  previous?: ReadyWeatherSection<Data> | StaleWeatherSection<Data>,
): RetryingWeatherSection<Data> {
  return previous ? { status: "retrying", previous } : { status: "retrying" };
}

export function isSourceStale(
  sourceUpdatedAt: string | null,
  staleAfterMs: number,
  now: Date = new Date(),
): boolean {
  if (sourceUpdatedAt === null) {
    return false;
  }
  const sourceTime = Date.parse(sourceUpdatedAt);
  return !Number.isFinite(sourceTime) || now.getTime() - sourceTime > staleAfterMs;
}

export function loadedWeatherSection<Data>(
  response: DataResponse<Data>,
  staleAfterMs: number,
  now: Date = new Date(),
): ReadyWeatherSection<Data> | StaleWeatherSection<Data> {
  const timestamps = {
    sourceUpdatedAt: response.meta.sourceUpdatedAt,
    fetchedAt: response.meta.fetchedAt,
  };
  if (isSourceStale(response.meta.sourceUpdatedAt, staleAfterMs, now)) {
    return {
      status: "stale",
      data: response.data,
      meta: response.meta,
      ...timestamps,
    };
  }
  return {
    status: "ready",
    data: response.data,
    meta: response.meta,
    ...timestamps,
  };
}

export function unavailableWeatherSection(
  error: unknown,
): UnavailableWeatherSection {
  if (error instanceof WeatherApiError) {
    return {
      status: "unavailable",
      error: {
        kind: error.kind,
        message: error.message,
        status: error.status,
      },
      canRetry: error.status === 404 || error.status === 503,
    };
  }
  return {
    status: "unavailable",
    error: {
      kind: "unexpected",
      message: error instanceof Error ? error.message : "Weather data unavailable",
      status: null,
    },
    canRetry: true,
  };
}

export async function loadWeatherSection<Data>(
  load: () => Promise<DataResponse<Data>>,
  staleAfterMs: number,
  now: Date = new Date(),
): Promise<WeatherSectionState<Data>> {
  try {
    return loadedWeatherSection(await load(), staleAfterMs, now);
  } catch (error) {
    return unavailableWeatherSection(error);
  }
}
