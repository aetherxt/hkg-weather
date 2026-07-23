import type { KeyboardEvent } from "react";

import { WeatherClouds } from "@/components/weather-clouds";
import type {
  WeatherDetailInteractionProps,
  WeatherDetailSection,
} from "@/components/weather-detail-sections";
import { getConditionTone } from "@/lib/weather/condition-tone";
import type { AstronomicalTimes } from "@/lib/weather/types";
import { getUvTone } from "@/lib/weather/uv-tone";

function formatUpdatedAt(iso: string) {
  const date = new Date(iso);
  const now = new Date();
  const hkTime = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Hong_Kong",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
  const todayHk = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Hong_Kong",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
  const timePart = date.toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: "Asia/Hong_Kong",
  });
  if (hkTime === todayHk) {
    return timePart;
  }
  const datePart = date.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "numeric",
    timeZone: "Asia/Hong_Kong",
  });
  return `${datePart}, ${timePart}`;
}

interface CurrentWeatherReportProps extends WeatherDetailInteractionProps {
  temperature: number | null;
  temperatureDistrict: string | null;
  condition: string | null;
  humidity: number | null;
  rainfall: number | null;
  updatedAt: string | null;
}

interface EnvironmentalConditionsProps extends WeatherDetailInteractionProps {
  uvIndex: number | null;
  uvLevel: string | null;
  astronomical: AstronomicalTimes | null;
}

function selectSectionWithKeyboard(
  event: KeyboardEvent<HTMLDivElement>,
  section: WeatherDetailSection,
  onSelectSection: WeatherDetailInteractionProps["onSelectSection"],
) {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    onSelectSection(section);
  }
}

function blueColor(value: number | null, max: number = 100): string | undefined {
  if (value === null || value <= 0) return undefined;
  const intensity = Math.min(value / max, 1);
  return `rgba(8, 62, 110, ${(0.08 + intensity * 0.74).toFixed(2)})`;
}

export function CurrentWeatherReport({
  temperature,
  temperatureDistrict,
  condition,
  humidity,
  rainfall,
  updatedAt,
  activeSection,
  onSelectSection,
}: CurrentWeatherReportProps) {
  return (
    <section className="current-weather" aria-label="Current weather">
      <div
        className="current-weather-temperature-block"
        data-condition-tone={condition ? getConditionTone(condition) : undefined}
      >
        <div className="current-weather-scene">
          <WeatherClouds />
          <div
            className="current-weather-temperature-row weather-data-trigger"
            data-weather-trigger="temperature"
            data-active={activeSection === "temperature" ? "true" : undefined}
            aria-controls="weather-detail-temperature-content"
            aria-expanded={activeSection === "temperature"}
            aria-label="Open temperature details"
            onClick={() => onSelectSection("temperature")}
            onKeyDown={(event) =>
              selectSectionWithKeyboard(event, "temperature", onSelectSection)
            }
            role="button"
            tabIndex={0}
          >
            <p className="current-weather-temperature" suppressHydrationWarning style={temperature !== null && temperature.toFixed(0).endsWith('7') ? { letterSpacing: '0em' } : undefined}>
              {temperature !== null ? (
                <>
                  {temperature.toFixed(0)}
                  <span aria-hidden="true">°</span>
                  <span className="sr-only"> degrees Celsius</span>
                </>
              ) : (
                <span className="current-weather-unavailable" aria-label="Unavailable">
                  --
                </span>
              )}
            </p>
            <span className="weather-row-chevron" aria-hidden="true" />
          </div>
        </div>
        {(updatedAt || temperatureDistrict) && (
          <p className="current-weather-updated-at" suppressHydrationWarning>
            {updatedAt && <>Last Updated At: {formatUpdatedAt(updatedAt)}</>}
            {temperatureDistrict && <span className="current-weather-district" suppressHydrationWarning>District: {temperatureDistrict}</span>}
          </p>
        )}
      </div>

      <div
        className="current-weather-condition-row weather-data-trigger"
        data-weather-trigger="rainfall-wind"
        data-active={activeSection === "rainfall-wind" ? "true" : undefined}
        aria-controls="weather-detail-rainfall-wind-content"
        aria-expanded={activeSection === "rainfall-wind"}
        aria-label="Open rainfall and wind details"
        onClick={() => onSelectSection("rainfall-wind")}
        onKeyDown={(event) =>
          selectSectionWithKeyboard(event, "rainfall-wind", onSelectSection)
        }
        role="button"
        tabIndex={0}
      >
        <p className="current-weather-meta">
          <span
            className="current-weather-stat-label"
            data-condition-tone={condition ? getConditionTone(condition) : undefined}
          >Humidity</span>
          {' '}
          {humidity !== null ? (
            <span className="current-weather-stat-value" style={{ color: blueColor(humidity) }}>
              {humidity}%
            </span>
          ) : (
            <span className="current-weather-unavailable">--</span>
          )}
          <span aria-hidden="true"> · </span>
          <span
            className="current-weather-stat-label"
            data-condition-tone={condition ? getConditionTone(condition) : undefined}
          >Rainfall</span>
          {' '}
          {rainfall !== null ? (
            <span className="current-weather-stat-value" style={{ color: blueColor(rainfall, 20) }}>
              {rainfall} mm
            </span>
          ) : (
            <span className="current-weather-unavailable">--</span>
          )}
        </p>
        <span className="weather-row-chevron" aria-hidden="true" />
      </div>

      {condition && (
        <p
          className="current-weather-meta"
          data-condition-tone={getConditionTone(condition)}
        >
          <span className="current-weather-forecast-label">Forecast: </span>
          <span className="current-weather-forecast-value">{condition}</span>
        </p>
      )}
    </section>
  );
}

export function EnvironmentalConditions({
  uvIndex,
  uvLevel,
  astronomical,
  activeSection,
  onSelectSection,
}: EnvironmentalConditionsProps) {
  return (
    <section className="environmental-conditions" aria-label="Environmental conditions">
      <div
        className="environmental-conditions-row weather-data-trigger"
        data-weather-trigger="uv"
        data-active={activeSection === "uv" ? "true" : undefined}
        aria-controls="weather-detail-uv-content"
        aria-expanded={activeSection === "uv"}
        aria-label="Open UV details"
        onClick={() => onSelectSection("uv")}
        onKeyDown={(event) =>
          selectSectionWithKeyboard(event, "uv", onSelectSection)
        }
        role="button"
        tabIndex={0}
      >
        <div className="environmental-conditions-values">
          <p data-uv-tone={uvIndex !== null ? getUvTone(uvIndex) : undefined}>
            <span>UV</span>{" "}
            {uvIndex !== null ? (
              <>{uvIndex} {uvLevel}</>
            ) : (
              <span className="current-weather-unavailable">Unavailable</span>
            )}
          </p>
          <p className="current-weather-sun-row">
            <span>Sun</span>{" "}
            {astronomical !== null ? (
              <>
                {astronomical.sunrise}
                <span className="sun-arrow-up" aria-hidden="true">↑</span>
                <span className="sun-dot" aria-hidden="true">·</span>
                {astronomical.sunset}
                <span className="sun-arrow-down" aria-hidden="true">↓</span>
              </>
            ) : (
              <span className="current-weather-unavailable">Unavailable</span>
            )}
          </p>
        </div>
        <span className="weather-row-chevron" aria-hidden="true" />
      </div>
    </section>
  );
}
