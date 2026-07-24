"use client";

import { useEffect, useState } from "react";

import { TyphoonTrackMap } from "@/components/typhoon-track-map";
import { weatherClient } from "@/lib/weather/client";
import type {
  ArchivedTropicalCyclone,
  TropicalCyclone,
} from "@/lib/weather/types";

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

export function TyphoonTrackPage() {
  const [cyclone, setCyclone] = useState<TropicalCyclone | null>(null);
  const [frames, setFrames] = useState<ArchivedTropicalCyclone[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [status, setStatus] = useState<"loading" | "ready" | "empty" | "error">(
    "loading",
  );

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
        setCyclone(selectedCyclone);
        setFrames(availableFrames);
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

  return (
    <main className="weather-page typhoon-page">
      <div className="typhoon-page-content">
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

          {status === "loading" ? (
            <p className="typhoon-page-state">Loading typhoon track…</p>
          ) : status === "empty" ? (
            <p className="typhoon-page-state">
              No active typhoon track is available.
            </p>
          ) : status === "error" ? (
            <p className="typhoon-page-state">
              The typhoon track is temporarily unavailable.
            </p>
          ) : selectedFrame ? (
            <section
              className="typhoon-timeline"
              aria-label="Archived track timeline"
            >
              <p className="typhoon-timeline-caption">
                Forecast snapshot {selectedIndex + 1} of {frames.length}
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
                <input
                  type="range"
                  min="0"
                  max={Math.max(0, frames.length - 1)}
                  step="1"
                  value={selectedIndex}
                  aria-label="Forecast snapshot"
                  onChange={(event) =>
                    setSelectedIndex(Number(event.currentTarget.value))
                  }
                />
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
              </div>
            </section>
          ) : null}
        </div>

        {status === "ready" && cyclone && selectedFrame ? (
          <div className="typhoon-page-map">
            <TyphoonTrackMap
              activeAsOf={cyclone.fetchedAt}
              activeGeoJson={cyclone.geoJson}
              asOf={selectedFrame.fetchedAt}
              geoJson={selectedFrame.geoJson}
              potentialTrackAreaGeoJson={
                selectedFrame.potentialTrackAreaGeoJson
              }
              key={selectedFrame.fetchedAt}
            />
          </div>
        ) : null}
      </div>
    </main>
  );
}
