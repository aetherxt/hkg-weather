import type { KeyboardEvent } from "react";

import type {
  WeatherDetailInteractionProps,
  WeatherDetailSection,
} from "@/components/weather-detail-sections";

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
  condition: string | null;
  humidity: number | null;
  rainfall: number | null;
  updatedAt: string | null;
}

interface EnvironmentalConditionsProps extends WeatherDetailInteractionProps {
  uvIndex: number | null;
  uvLevel: string | null;
  airQuality: string | null;
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

function getConditionTone(condition: string) {
  const normalizedCondition = condition.toLowerCase();

  if (
    normalizedCondition.includes("shower") ||
    normalizedCondition.includes("rain") ||
    normalizedCondition.includes("drizzle") ||
    normalizedCondition.includes("thunder")
  ) {
    return "rain";
  }

  if (
    normalizedCondition.includes("cloud") ||
    normalizedCondition.includes("overcast")
  ) {
    return "cloudy";
  }

  if (
    normalizedCondition.includes("sun") ||
    normalizedCondition.includes("fine") ||
    normalizedCondition.includes("clear")
  ) {
    return "sunny";
  }

  return "neutral";
}

function getUvTone(uvIndex: number) {
  if (uvIndex <= 2) return "low";
  if (uvIndex <= 5) return "moderate";
  if (uvIndex <= 7) return "high";
  if (uvIndex <= 10) return "very-high";
  return "extreme";
}

function getAirQualityTone(airQuality: string) {
  const normalizedAirQuality = airQuality.toLowerCase();

  if (
    normalizedAirQuality.includes("serious") ||
    normalizedAirQuality.includes("hazardous")
  ) {
    return "serious";
  }

  if (normalizedAirQuality.includes("very high")) return "very-high";
  if (normalizedAirQuality.includes("high")) return "high";
  if (normalizedAirQuality.includes("moderate")) return "moderate";
  if (
    normalizedAirQuality.includes("low") ||
    normalizedAirQuality.includes("poor") ||
    normalizedAirQuality.includes("unhealthy")
  ) {
    return "low";
  }
  if (normalizedAirQuality.includes("good")) return "high";

  return "neutral";
}

export function CurrentWeatherReport({
  temperature,
  condition,
  humidity,
  rainfall,
  updatedAt,
  activeSection,
  onSelectSection,
}: CurrentWeatherReportProps) {
  return (
    <section className="current-weather" aria-label="Current weather">
      <div className="current-weather-temperature-block">
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
          <p className="current-weather-temperature">
            {temperature !== null ? (
              <>
                {temperature}
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
        {updatedAt && (
          <p className="current-weather-updated-at">
            Last Updated At: {formatUpdatedAt(updatedAt)}
          </p>
        )}
      </div>

      <div
        className="current-weather-condition-row weather-data-trigger"
        data-weather-trigger="precipitation"
        data-active={activeSection === "precipitation" ? "true" : undefined}
        aria-controls="weather-detail-precipitation-content"
        aria-expanded={activeSection === "precipitation"}
        aria-label="Open precipitation details"
        onClick={() => onSelectSection("precipitation")}
        onKeyDown={(event) =>
          selectSectionWithKeyboard(event, "precipitation", onSelectSection)
        }
        role="button"
        tabIndex={0}
      >
        <p
          className="current-weather-condition"
          data-condition-tone={condition ? getConditionTone(condition) : undefined}
        >
          {condition ?? <span className="current-weather-unavailable">--</span>}
        </p>
        <span className="weather-row-chevron" aria-hidden="true" />
      </div>

      <p className="current-weather-meta">
        {humidity !== null ? (
          <>Humidity {humidity}%</>
        ) : (
          <>Humidity <span className="current-weather-unavailable">--</span></>
        )}
        <span aria-hidden="true"> · </span>
        {rainfall !== null ? (
          <>Rainfall {rainfall} mm</>
        ) : (
          <>Rainfall <span className="current-weather-unavailable">--</span></>
        )}
      </p>
    </section>
  );
}

export function EnvironmentalConditions({
  uvIndex,
  uvLevel,
  airQuality,
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
          <p data-air-quality-tone={airQuality ? getAirQualityTone(airQuality) : undefined}>
            <span>Air quality</span>{" "}
            {airQuality ?? (
              <span className="current-weather-unavailable">Unavailable</span>
            )}
          </p>
        </div>
        <span className="weather-row-chevron" aria-hidden="true" />
      </div>
    </section>
  );
}
