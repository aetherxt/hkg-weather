import type { WeatherClient } from "./client.ts";
import {
  loadedWeatherSection,
  unavailableWeatherSection,
  type WeatherSectionState,
} from "./state.ts";
import type {
  AstronomicalTimes,
  CurrentWeather,
  DashboardSnapshot,
  DataResponse,
  LamppostReading,
  LocalForecast,
  NineDayForecast,
  StationRainfallResponse,
  TemperatureReading,
  Warnings,
  WindReading,
} from "./types.ts";

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;

export const INITIAL_WEATHER_STALE_AFTER = {
  warnings: 30 * MINUTE,
  current: 90 * MINUTE,
  localForecast: 12 * HOUR,
  nineDayForecast: 18 * HOUR,
  regionalTemperature: 30 * MINUTE,
  regionalWind: 30 * MINUTE,
  lampposts: 30 * MINUTE,
  astronomical: 24 * HOUR,
  stationRainfall: 30 * MINUTE,
} as const;

export interface InitialWeatherState {
  warnings: WeatherSectionState<Warnings>;
  current: WeatherSectionState<CurrentWeather>;
  localForecast: WeatherSectionState<LocalForecast>;
  nineDayForecast: WeatherSectionState<NineDayForecast>;
  regionalTemperature: WeatherSectionState<TemperatureReading[]>;
  regionalWind: WeatherSectionState<WindReading[]>;
  lampposts: WeatherSectionState<LamppostReading[]>;
  astronomical: WeatherSectionState<AstronomicalTimes>;
  stationRainfall: WeatherSectionState<StationRainfallResponse>;
}

function dashboardSection<Data>(
  response: DataResponse<Data> | null,
  staleAfterMs: number,
  now: Date,
): WeatherSectionState<Data> {
  if (response === null) {
    return {
      status: "unavailable",
      error: {
        kind: "unavailable",
        message: "Weather data unavailable",
        status: 503,
      },
      canRetry: true,
    };
  }
  return loadedWeatherSection(response, staleAfterMs, now);
}

function unavailableInitialWeather(error: unknown): InitialWeatherState {
  return {
    warnings: unavailableWeatherSection(error),
    current: unavailableWeatherSection(error),
    localForecast: unavailableWeatherSection(error),
    nineDayForecast: unavailableWeatherSection(error),
    regionalTemperature: unavailableWeatherSection(error),
    regionalWind: unavailableWeatherSection(error),
    lampposts: unavailableWeatherSection(error),
    astronomical: unavailableWeatherSection(error),
    stationRainfall: unavailableWeatherSection(error),
  };
}

export function initialWeatherFromDashboard(
  dashboard: DashboardSnapshot,
  now: Date = new Date(),
): InitialWeatherState {
  return {
    warnings: dashboardSection(
      dashboard.warnings,
      INITIAL_WEATHER_STALE_AFTER.warnings,
      now,
    ),
    current: dashboardSection(
      dashboard.current,
      INITIAL_WEATHER_STALE_AFTER.current,
      now,
    ),
    localForecast: dashboardSection(
      dashboard.localForecast,
      INITIAL_WEATHER_STALE_AFTER.localForecast,
      now,
    ),
    nineDayForecast: dashboardSection(
      dashboard.nineDayForecast,
      INITIAL_WEATHER_STALE_AFTER.nineDayForecast,
      now,
    ),
    regionalTemperature: dashboardSection(
      dashboard.regionalTemperature,
      INITIAL_WEATHER_STALE_AFTER.regionalTemperature,
      now,
    ),
    regionalWind: dashboardSection(
      dashboard.regionalWind,
      INITIAL_WEATHER_STALE_AFTER.regionalWind,
      now,
    ),
    lampposts: dashboardSection(
      dashboard.lampposts,
      INITIAL_WEATHER_STALE_AFTER.lampposts,
      now,
    ),
    astronomical: dashboardSection(
      dashboard.astronomical,
      INITIAL_WEATHER_STALE_AFTER.astronomical,
      now,
    ),
    stationRainfall: dashboardSection(
      dashboard.stationRainfall,
      INITIAL_WEATHER_STALE_AFTER.stationRainfall,
      now,
    ),
  };
}

export async function loadInitialWeather(
  client: WeatherClient,
  now: Date = new Date(),
): Promise<InitialWeatherState> {
  try {
    const response = await client.getDashboard();
    return initialWeatherFromDashboard(response.data, now);
  } catch (error) {
    return unavailableInitialWeather(error);
  }
}
