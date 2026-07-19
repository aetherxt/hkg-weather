import type { WeatherClient } from "./client.ts";
import { loadWeatherSection, type WeatherSectionState } from "./state.ts";
import type {
  AstronomicalTimes,
  CurrentWeather,
  LamppostReading,
  LocalForecast,
  NineDayForecast,
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
}

export async function loadInitialWeather(
  client: WeatherClient,
  now: Date = new Date(),
): Promise<InitialWeatherState> {
  const [
    warnings,
    current,
    localForecast,
    nineDayForecast,
    regionalTemperature,
    regionalWind,
    lampposts,
    astronomical,
  ] = await Promise.all([
    loadWeatherSection(
      client.getWarnings,
      INITIAL_WEATHER_STALE_AFTER.warnings,
      now,
    ),
    loadWeatherSection(
      client.getCurrentWeather,
      INITIAL_WEATHER_STALE_AFTER.current,
      now,
    ),
    loadWeatherSection(
      client.getLocalForecast,
      INITIAL_WEATHER_STALE_AFTER.localForecast,
      now,
    ),
    loadWeatherSection(
      client.getNineDayForecast,
      INITIAL_WEATHER_STALE_AFTER.nineDayForecast,
      now,
    ),
    loadWeatherSection(
      client.getRegionalTemperature,
      INITIAL_WEATHER_STALE_AFTER.regionalTemperature,
      now,
    ),
    loadWeatherSection(
      client.getRegionalWind,
      INITIAL_WEATHER_STALE_AFTER.regionalWind,
      now,
    ),
    loadWeatherSection(
      client.getLampposts,
      INITIAL_WEATHER_STALE_AFTER.lampposts,
      now,
    ),
    loadWeatherSection(
      client.getAstronomicalTimes,
      INITIAL_WEATHER_STALE_AFTER.astronomical,
      now,
    ),
  ]);

  return {
    warnings,
    current,
    localForecast,
    nineDayForecast,
    regionalTemperature,
    regionalWind,
    lampposts,
    astronomical,
  };
}
