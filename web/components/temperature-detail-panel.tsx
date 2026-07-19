"use client";

import type { WeatherSectionState } from "@/lib/weather/state";
import type {
  LamppostReading,
  TemperatureReading,
} from "@/lib/weather/types";

function formatTime(iso: string) {
  const date = new Date(iso);
  return date.toLocaleTimeString("en-HK", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function TemperatureReadingRow({
  station,
  temperatureC,
}: { station: string; temperatureC: number | null }) {
  return (
    <div className="temperature-station-row">
      <span className="temperature-station-name">{station}</span>
      <span className="temperature-station-value">
        {temperatureC !== null ? (
          <>
            {temperatureC}
            <span aria-hidden="true">°</span>
            <span className="sr-only"> degrees Celsius</span>
          </>
        ) : (
          <span className="weather-value-unavailable" aria-label="Unavailable">
            --
          </span>
        )}
      </span>
    </div>
  );
}

function RegionalTemperatureSection({
  readings,
  sourceUpdatedAt,
}: {
  readings: TemperatureReading[];
  sourceUpdatedAt: string | null;
}) {
  return (
    <div className="temperature-subsection">
      <h3 className="temperature-subsection-title">Regional stations</h3>
      {sourceUpdatedAt && (
        <p className="temperature-subsection-time">
          Observed at {formatTime(sourceUpdatedAt)}
        </p>
      )}
      <div className="temperature-station-list">
        {readings.map((reading) => (
          <TemperatureReadingRow
            key={reading.station}
            station={reading.station}
            temperatureC={reading.temperatureC}
          />
        ))}
      </div>
    </div>
  );
}

function LamppostRow({
  label,
  reading,
}: { label: string; reading: Record<string, unknown> }) {
  const hko = reading?.body && typeof reading.body === "object" && "hko" in reading.body
    ? (reading.body as Record<string, unknown>).hko as Record<string, unknown>
    : null;
  const temperature = hko?.t0;
  const humidity = hko?.rh;

  return (
    <div className="lamppost-row">
      <span className="lamppost-label">{label}</span>
      <span className="lamppost-values">
        {temperature ? (
          <span>
            {temperature as string}
            <span aria-hidden="true">°</span>
            <span className="sr-only"> degrees Celsius</span>
          </span>
        ) : null}
        {temperature && humidity ? (
          <span className="lamppost-separator" aria-hidden="true" />
        ) : null}
        {humidity ? (
          <span>
            {(humidity as string)}
            <span className="sr-only"> percent humidity</span>
            <span aria-hidden="true">%</span>
          </span>
        ) : null}
        {!temperature && !humidity ? (
          <span className="weather-value-unavailable">--</span>
        ) : null}
      </span>
    </div>
  );
}

function LamppostSection({
  readings,
}: {
  readings: LamppostReading[];
}) {
  return (
    <div className="temperature-subsection">
      <h3 className="temperature-subsection-title">Smart lamppost readings</h3>
      <div className="lamppost-list">
        {readings.map((lp) => (
          <LamppostRow
            key={`${lp.lamppostId}:${lp.deviceId}`}
            label={lp.label}
            reading={lp.reading}
          />
        ))}
      </div>
    </div>
  );
}

function UnavailableMessage({ label }: { label: string }) {
  return (
    <p className="temperature-unavailable">
      {label} data is currently unavailable
    </p>
  );
}

export function TemperatureDetailPanel({
  regionalTemperature,
  lampposts,
}: {
  regionalTemperature: WeatherSectionState<TemperatureReading[]>;
  lampposts: WeatherSectionState<LamppostReading[]>;
}) {
  return (
    <div className="temperature-detail-panel">
      {regionalTemperature.status === "ready" ||
      regionalTemperature.status === "stale" ? (
        <RegionalTemperatureSection
          readings={regionalTemperature.data}
          sourceUpdatedAt={regionalTemperature.sourceUpdatedAt}
        />
      ) : regionalTemperature.status === "loading" ||
        regionalTemperature.status === "retrying" ? (
        <div className="temperature-subsection">
          <h3 className="temperature-subsection-title">Regional stations</h3>
          <p className="temperature-loading">Loading regional data...</p>
        </div>
      ) : (
        <UnavailableMessage label="Regional temperature" />
      )}

      {lampposts.status === "ready" || lampposts.status === "stale" ? (
        <LamppostSection readings={lampposts.data} />
      ) : lampposts.status === "loading" ||
        lampposts.status === "retrying" ? (
        <div className="temperature-subsection">
          <h3 className="temperature-subsection-title">
            Smart lamppost readings
          </h3>
          <p className="temperature-loading">Loading lamppost data...</p>
        </div>
      ) : (
        <UnavailableMessage label="Smart lamppost" />
      )}
    </div>
  );
}
