"use client";

import type { WeatherSectionState } from "@/lib/weather/state";
import type {
  DistrictRainfallReading,
  StationRainfallResponse,
} from "@/lib/weather/types";

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString("en-HK", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Hong_Kong",
  });
}

function rainfallMm(value: string): number | null {
  if (value === "M" || value === "NIL") return null;
  const parsed = parseFloat(value);
  return isNaN(parsed) ? null : parsed;
}

function districtSection(readings: DistrictRainfallReading[]) {
  return (
    <section className="rw-section">
      <div className="rw-section-header">
        <h3 className="rw-section-heading">District Rainfall</h3>
      </div>
      {readings.length === 0 ? (
        <p className="rw-unavailable">Unavailable</p>
      ) : (
        <div className="rw-grid">
          {readings.map((r) => (
            <div className="rw-card" key={r.place}>
              <span className="rw-card-value">
                {r.max}
                <span className="rw-unit">mm</span>
              </span>
              <span className="rw-card-label">{r.place}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function stationSection(
  section: WeatherSectionState<StationRainfallResponse> | undefined,
) {
  if (
    !section ||
    (section.status !== "ready" && section.status !== "stale")
  ) {
    return (
      <section className="rw-section">
        <h3 className="rw-section-heading">Station Rainfall (past hour)</h3>
        <p className="rw-unavailable">Unavailable</p>
      </section>
    );
  }

  const readings = section.data.hourlyRainfall;
  const updatedAt = section.sourceUpdatedAt ?? section.fetchedAt;

  return (
    <section className="rw-section">
      <div className="rw-section-header">
        <h3 className="rw-section-heading">Station Rainfall (past hour)</h3>
        {updatedAt && (
          <span className="rw-updated-at">{formatTime(updatedAt)}</span>
        )}
      </div>
      <div className="rw-grid">
        {readings.map((r, i) => (
          <div className="rw-card" key={`${r.automaticWeatherStationID}-${i}`}>
            <span className="rw-card-value">
              {rainfallMm(r.value) ?? "--"}
              <span className="rw-unit">mm</span>
            </span>
            <span className="rw-card-label">{r.automaticWeatherStation}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

export function RainfallDetailPanel({
  rainfallReadings,
  stationRainfall,
}: {
  rainfallReadings: DistrictRainfallReading[];
  stationRainfall: WeatherSectionState<StationRainfallResponse>;
}) {
  return (
    <div className="rw-panel">
      {stationSection(stationRainfall)}
      {districtSection(rainfallReadings)}
    </div>
  );
}