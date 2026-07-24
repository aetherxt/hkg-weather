"use client";

import { useEffect, useMemo, useState } from "react";

import { TyphoonTrackMap } from "@/components/typhoon-track-map";
import { weatherClient } from "@/lib/weather/client";
import type {
  ArchivedModelRainfall,
  ArchivedModelWind,
  ArchivedTropicalCyclone,
  TropicalCyclone,
} from "@/lib/weather/types";

export interface TyphoonModelFrame {
  validAt: string;
  rainfall: ArchivedModelRainfall;
  wind: ArchivedModelWind | null;
}

interface TyphoonModelResult {
  frame: TyphoonModelFrame | null;
  snapshotTime: string;
}

const FORECAST_INTERVAL_HOURS = 3;

function formatSnapshotTime(value: string) {
  return new Intl.DateTimeFormat("en-HK", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Hong_Kong",
    timeZoneName: "short",
  }).format(new Date(value));
}

function currentFrame(
  cyclone: TropicalCyclone,
): ArchivedTropicalCyclone {
  return cyclone;
}

function uniqueFrames(frames: ArchivedTropicalCyclone[]) {
  const byTrack = new Map<string, ArchivedTropicalCyclone>();
  frames.forEach((frame) => {
    const key = JSON.stringify([
      frame.geoJson,
      frame.potentialTrackAreaGeoJson,
    ]);
    const previous = byTrack.get(key);
    if (!previous || previous.fetchedAt < frame.fetchedAt) {
      byTrack.set(key, frame);
    }
  });
  return Array.from(byTrack.values()).sort((first, second) =>
    first.fetchedAt.localeCompare(second.fetchedAt),
  );
}

const FORECAST_MONTHS = [
  "january", "february", "march", "april", "may", "june",
  "july", "august", "september", "october", "november", "december",
];

function parseHkoDate(value: string): number | null {
  const full = value.match(
    /(\d{1,2}):(\d{2})\s*HKT\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})/i,
  );
  if (full) {
    const month = FORECAST_MONTHS.indexOf(full[4].toLowerCase());
    if (month < 0) return null;
    return Date.UTC(
      Number(full[5]), month, Number(full[3]),
      Number(full[1]) - 8, Number(full[2]),
    );
  }
  const compact = value.match(
    /(\d{1,2})\s+([A-Za-z]+),?\s+(\d{1,2})(?::(\d{2}))?\s*HKT/i,
  );
  if (compact) {
    const month = FORECAST_MONTHS.findIndex((c) =>
      c.startsWith(compact[2].toLowerCase()),
    );
    if (month < 0) return null;
    const now = new Date();
    const year = now.getUTCFullYear();
    const candidate = Date.UTC(year, month, Number(compact[1]));
    if (candidate > Date.UTC(year, now.getUTCMonth(), now.getUTCDate() + 60))
      return null;
    return Date.UTC(
      year, month, Number(compact[1]),
      Number(compact[3]) - 8, compact[4] ? Number(compact[4]) : 0,
    );
  }
  return null;
}

function extractFeatureTime(feature: Record<string, unknown>): number | null {
  const properties =
    typeof feature.properties === "object" && feature.properties !== null
      ? feature.properties as Record<string, unknown>
      : {};
  const raw =
    typeof properties.dateTime === "string"
      ? properties.dateTime
      : typeof properties.description === "string"
        ? (() => {
            const escaped = "Date and time".replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
            const m = properties.description.match(
              new RegExp(`${escaped}<\\/th>\\s*<td[^>]*>([\\s\\S]*?)<\\/td>`, "i"),
            );
            return m?.[1]?.replace(/<[^>]+>/g, "").replace(/&amp;/gi, "&").trim() ?? null;
          })()
        : null;
  return typeof raw === "string" ? parseHkoDate(raw) : null;
}

function findLastForecastTimeMs(geoJson: Record<string, unknown>): number | null {
  if (!Array.isArray(geoJson.features)) return null;
  let latest: number | null = null;
  for (const feature of geoJson.features) {
    if (typeof feature !== "object" || feature === null) continue;
    const geometry = (feature as Record<string, unknown>).geometry;
    if (typeof geometry !== "object" || geometry === null) continue;
    if ((geometry as Record<string, unknown>).type !== "Point") continue;
    const parsed = extractFeatureTime(feature as Record<string, unknown>);
    if (parsed !== null && (latest === null || parsed > latest)) {
      latest = parsed;
    }
  }
  return latest;
}

function generateFutureSlots(
  fromTime: string,
  toTimeMs: number,
  template: ArchivedTropicalCyclone,
): ArchivedTropicalCyclone[] {
  const slots: ArchivedTropicalCyclone[] = [];
  const fromMs = Date.parse(fromTime);
  const intervalMs = FORECAST_INTERVAL_HOURS * 60 * 60 * 1000;
  let currentMs = Math.ceil(fromMs / intervalMs) * intervalMs;
  while (currentMs <= toTimeMs) {
    slots.push({
      stormId: template.stormId,
      nameEn: template.nameEn,
      nameZh: template.nameZh,
      fetchedAt: new Date(currentMs).toISOString(),
      geoJson: template.geoJson,
      potentialTrackAreaGeoJson: template.potentialTrackAreaGeoJson,
    });
    currentMs += intervalMs;
  }
  return slots;
}

export function TyphoonTrackPage() {
  const [cyclone, setCyclone] = useState<TropicalCyclone | null>(null);
  const [frames, setFrames] = useState<ArchivedTropicalCyclone[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [modelResult, setModelResult] = useState<TyphoonModelResult | null>(
    null,
  );
  const [status, setStatus] = useState<"loading" | "ready" | "empty" | "error">(
    "loading",
  );

  const latestSnapshotIndex = useMemo(() => {
    if (!cyclone) return 0;
    const latestTime = Date.parse(cyclone.fetchedAt);
    let latest = 0;
    for (let i = 0; i < frames.length; i++) {
      if (Date.parse(frames[i].fetchedAt) <= latestTime) {
        latest = i;
      }
    }
    return latest;
  }, [cyclone, frames]);

  useEffect(() => {
    const controller = new AbortController();

    const loadTrack = async () => {
      try {
        const active = await weatherClient.getTropicalCyclones({
          signal: controller.signal,
        });
        const selectedCyclone = active.data[0];
        if (!selectedCyclone) {
          setStatus("empty");
          return;
        }

        const to = new Date();
        const from = new Date(to.getTime() - 3 * 24 * 60 * 60 * 1000);
        let archived: ArchivedTropicalCyclone[] = [];
        try {
          const history = await weatherClient.getTropicalCycloneHistory(
            selectedCyclone.stormId,
            from.toISOString(),
            to.toISOString(),
            { signal: controller.signal },
          );
          archived = history.data;
        } catch {
          if (controller.signal.aborted) return;
        }

        const latest = currentFrame(selectedCyclone);
        const availableFrames = uniqueFrames([
          ...archived,
          latest,
        ]);

        const lastForecastMs = findLastForecastTimeMs(latest.geoJson);
        const futureSlots =
          lastForecastMs !== null && lastForecastMs > Date.parse(latest.fetchedAt)
            ? generateFutureSlots(latest.fetchedAt, lastForecastMs, latest)
            : [];
        setCyclone(selectedCyclone);
        setFrames([...availableFrames, ...futureSlots]);
        setSelectedIndex(Math.max(0, availableFrames.length - 1));
        setStatus(availableFrames.length > 0 ? "ready" : "empty");
      } catch {
        if (!controller.signal.aborted) setStatus("error");
      }
    };

    void loadTrack();
    return () => controller.abort();
  }, []);

  const selectedFrame = frames[selectedIndex] ?? null;
  const latestFrame = cyclone ? currentFrame(cyclone) : null;
  const isFutureSlot = selectedFrame !== null && latestFrame !== null &&
    Date.parse(selectedFrame.fetchedAt) > Date.parse(latestFrame.fetchedAt);

  useEffect(() => {
    if (!selectedFrame) return;
    const controller = new AbortController();
    const selectedTime = Date.parse(selectedFrame.fetchedAt);
    const rangeMs = 3 * 24 * 60 * 60 * 1000;
    const from = new Date(selectedTime - rangeMs / 2).toISOString();
    const to = new Date(selectedTime + rangeMs / 2).toISOString();

    const loadModelFrame = async () => {
      try {
        const [rainfall, wind] = await Promise.all([
          weatherClient.getModelRainfallHistory("ec", from, to, {
            signal: controller.signal,
          }),
          weatherClient.getModelWindHistory("ec", from, to, {
            signal: controller.signal,
          }),
        ]);
        const windByValidTime = new Map(
          wind.data.map((frame) => [
            `${Date.parse(frame.cycle)}|${Date.parse(frame.validAt)}`,
            frame,
          ]),
        );
        const candidates = rainfall.data
          .flatMap((rainFrame) => {
            const validTime = Date.parse(rainFrame.validAt);
            if (!Number.isFinite(validTime)) return [];
            return [{
              cycle: rainFrame.cycle,
              cycleTime: Date.parse(rainFrame.cycle),
              validAt: rainFrame.validAt,
              rainfall: rainFrame,
              wind:
                windByValidTime.get(
                  `${Date.parse(rainFrame.cycle)}|${validTime}`,
                ) ?? null,
              validTime,
            }];
          });
        const closest = (paired: boolean) =>
          candidates
            .filter((candidate) => !paired || candidate.wind !== null)
            .sort(
              (first, second) => {
                const distance =
                  Math.abs(first.validTime - selectedTime) -
                  Math.abs(second.validTime - selectedTime);
                return distance || second.cycleTime - first.cycleTime;
              },
            )[0];
        const selected = closest(true) ?? closest(false);
        const modelFrame = selected
          ? {
              validAt: selected.validAt,
              rainfall: selected.rainfall,
              wind: selected.wind,
            }
          : null;
        if (controller.signal.aborted) return;
        setModelResult({
          frame: modelFrame,
          snapshotTime: selectedFrame.fetchedAt,
        });
      } catch {
        if (!controller.signal.aborted) {
          setModelResult({
            frame: null,
            snapshotTime: selectedFrame.fetchedAt,
          });
        }
      }
    };

    void loadModelFrame();
    return () => controller.abort();
  }, [selectedFrame]);

  const currentModelResult =
    selectedFrame &&
    modelResult?.snapshotTime === selectedFrame.fetchedAt
      ? modelResult
      : null;
  const modelFrame = currentModelResult?.frame ?? null;
  const modelStatus: "idle" | "loading" | "ready" | "unavailable" =
    !selectedFrame
      ? "idle"
      : !currentModelResult
        ? "loading"
        : currentModelResult.frame
          ? "ready"
          : "unavailable";

  const loaded = status === "ready" && cyclone && selectedFrame;

  return (
    <main className="weather-page typhoon-page">
      <div className="typhoon-page-content">
        {loaded ? (
          <>
            <div className="typhoon-page-sidebar">
              <header className="typhoon-page-header">
                <h1>
                  Typhoon Track{cyclone ? ` (${cyclone.stormId})` : ""}
                  {cyclone ? (
                    <span className="typhoon-page-name">
                      {cyclone.nameEn}
                      {cyclone.nameZh ? ` · ${cyclone.nameZh}` : ""}
                    </span>
                  ) : null}
                </h1>
              </header>

              {selectedFrame ? (
                <section
                  className="typhoon-timeline"
                  aria-label="Archived track timeline"
                >
                  <p className="typhoon-timeline-caption">
                    {isFutureSlot ? "Future prediction" : "Forecast snapshot"} {selectedIndex + 1} of {frames.length}
                    <span aria-hidden="true"> · </span>
                    {formatSnapshotTime(selectedFrame.fetchedAt)}
                  </p>
                  <div className="typhoon-timeline-controls">
                    <button
                      type="button"
                      aria-label="Previous forecast snapshot"
                      disabled={selectedIndex === 0}
                      onClick={() =>
                        setSelectedIndex((index) => Math.max(0, index - 1))
                      }
                    >
                      <svg viewBox="0 0 18 18" aria-hidden="true">
                        <path d="m11.5 4.5-4.5 4.5 4.5 4.5" />
                      </svg>
                    </button>
                    <div className="typhoon-timeline-slider">
                      <input
                        type="range"
                        className="typhoon-timeline-input"
                        min="0"
                        max={Math.max(0, frames.length - 1)}
                        step="1"
                        value={selectedIndex}
                        aria-label="Forecast snapshot"
                        onChange={(event) =>
                          setSelectedIndex(Number(event.currentTarget.value))
                        }
                      />
                      <input
                        type="range"
                        className="typhoon-timeline-marker"
                        min="0"
                        max={Math.max(0, frames.length - 1)}
                        step="1"
                        value={latestSnapshotIndex}
                        tabIndex={-1}
                        aria-hidden="true"
                        disabled
                      />
                    </div>
                    <button
                      type="button"
                      aria-label="Next forecast snapshot"
                      disabled={selectedIndex >= frames.length - 1}
                      onClick={() =>
                        setSelectedIndex((index) =>
                          Math.min(frames.length - 1, index + 1),
                        )
                      }
                    >
                      <svg viewBox="0 0 18 18" aria-hidden="true">
                        <path d="m6.5 4.5 4.5 4.5-4.5 4.5" />
                      </svg>
                    </button>
                    <button
                      type="button"
                      aria-label="Return to current snapshot"
                      disabled={selectedIndex === latestSnapshotIndex}
                      onClick={() => setSelectedIndex(latestSnapshotIndex)}
                      className="typhoon-timeline-reset"
                    >
                      <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M21 12a9 9 0 1 1-3-6.7" />
                        <path d="M21 3v5h-5" />
                      </svg>
                    </button>
                  </div>
                </section>
              ) : null}
            </div>

            <div className="typhoon-page-map">
              <TyphoonTrackMap
                activeAsOf={cyclone.fetchedAt}
                activeGeoJson={cyclone.geoJson}
                asOf={selectedFrame.fetchedAt}
                geoJson={isFutureSlot ? cyclone.geoJson : selectedFrame.geoJson}
                potentialTrackAreaGeoJson={isFutureSlot ? cyclone.potentialTrackAreaGeoJson : selectedFrame.potentialTrackAreaGeoJson}
                modelFrame={modelFrame}
                modelStatus={modelStatus}
                isFuture={isFutureSlot}
                key={selectedFrame.fetchedAt}
              />
            </div>
          </>
        ) : status === "empty" ? (
          <div className="typhoon-page-sidebar">
            <header className="typhoon-page-header">
              <h1>Typhoon Track</h1>
            </header>
            <p className="typhoon-page-state">
              No active typhoon track is available.
            </p>
          </div>
        ) : status === "error" ? (
          <div className="typhoon-page-sidebar">
            <header className="typhoon-page-header">
              <h1>Typhoon Track</h1>
            </header>
            <p className="typhoon-page-state">
              The typhoon track is temporarily unavailable.
            </p>
          </div>
        ) : (
          <>
            <div className="typhoon-page-skeleton-sidebar">
              <div className="typhoon-skeleton typhoon-skeleton-header" />
              <div className="typhoon-skeleton typhoon-skeleton-caption" />
              <div className="typhoon-skeleton-controls">
                <div className="typhoon-skeleton typhoon-skeleton-button" />
                <div className="typhoon-skeleton typhoon-skeleton-slider" />
                <div className="typhoon-skeleton typhoon-skeleton-button" />
              </div>
            </div>
            <div className="typhoon-page-map">
              <div className="typhoon-skeleton-map">
                <div className="typhoon-skeleton typhoon-skeleton-map-inner" />
              </div>
            </div>
          </>
        )}
      </div>
    </main>
  );
}
