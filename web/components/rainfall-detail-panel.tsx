"use client";

import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import type { WeatherSectionState } from "@/lib/weather/state";
import type {
  LocalForecast,
  StationRainfallResponse,
} from "@/lib/weather/types";
import {
  type RainfallStationItem,
  buildRainfallStationItems,
  groupRainfallStations,
  normalizeRainfallRegionOrder,
  rainfallDefaultRegionOrder,
} from "@/lib/weather/rainfall-regions";
import type { TemperatureRegionId } from "@/lib/weather/temperature-regions";

const HIDDEN_RAINFALL_COOKIE = "hkw-hidden-rainfall-stations";
const REGION_ORDER_COOKIE = "hkw-rainfall-region-order";

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString("en-HK", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Hong_Kong",
  });
}

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(`(?:^|; )${name}=([^;]*)`);
  return match ? decodeURIComponent(match[1]) : null;
}

function setCookie(name: string, value: string) {
  document.cookie = `${name}=${encodeURIComponent(value)}; path=/; max-age=31536000; SameSite=Lax`;
}

function rainfallMm(value: string): number | null {
  if (value === "M" || value === "NIL") return null;
  const parsed = parseFloat(value);
  return isNaN(parsed) ? null : parsed;
}

function forecastSection(
  section: WeatherSectionState<LocalForecast> | undefined,
) {
  if (
    !section ||
    (section.status !== "ready" && section.status !== "stale")
  ) {
    return null;
  }

  const { forecastPeriod, forecastDesc, outlook } = section.data;
  const updatedAt = section.sourceUpdatedAt ?? section.fetchedAt;

  if (!forecastDesc) return null;

  return (
    <section className="rw-section">
      <div className="rw-section-header">
        <h3 className="rw-section-heading">Local Weather Forecast</h3>
        {updatedAt && (
          <span className="rw-updated-at">Updated At: {formatTime(updatedAt)}</span>
        )}
      </div>
      {forecastPeriod && (
        <p className="rw-forecast-period">{forecastPeriod}</p>
      )}
      <p className="rw-forecast-desc">{forecastDesc}</p>
      {outlook && (
        <p className="rw-forecast-outlook">
          <span className="rw-forecast-outlook-label">Outlook: </span>
          {outlook}
        </p>
      )}
    </section>
  );
}

function rainfallValue(value: number | null) {
  if (value === null) return "--";
  return value;
}

function RainfallStationCard({ item }: { item: RainfallStationItem }) {
  return (
    <div className="temperature-station-row">
      <span className="temperature-station-name">{item.label}</span>
      <span className="temperature-station-value">
        {rainfallValue(item.value)}
        <span className="rw-unit">mm</span>
      </span>
    </div>
  );
}

function RainfallRegionGrid({
  items,
  regionOrder,
}: {
  items: RainfallStationItem[];
  regionOrder: readonly TemperatureRegionId[];
}) {
  const groups = groupRainfallStations(items, regionOrder);

  return (
    <div className="temperature-region-list">
      {groups.map((group) => (
        <section key={group.id} className="temperature-region-group">
          <div className="temperature-region-header">
            <h3 className="temperature-subsection-title">{group.label}</h3>
            <span className="temperature-region-count">{group.items.length}</span>
          </div>
          <div className="temperature-station-list">
            {group.items.map((item) => (
              <RainfallStationCard key={item.id} item={item} />
            ))}
          </div>
        </section>
      ))}
      <p className="rw-info">
        Station rainfall is measured by tipping-bucket rain gauges at each automatic weather station,
        reporting accumulated rainfall over the past hour.
      </p>
    </div>
  );
}

function countItems(items: RainfallStationItem[]) {
  return items.length;
}

function moveRegion(
  regionOrder: readonly TemperatureRegionId[],
  regionId: TemperatureRegionId,
  direction: -1 | 1,
) {
  const index = regionOrder.indexOf(regionId);
  const nextIndex = index + direction;
  if (index === -1 || nextIndex < 0 || nextIndex >= regionOrder.length) return [...regionOrder];

  const next = [...regionOrder];
  const [moved] = next.splice(index, 1);
  next.splice(nextIndex, 0, moved);
  return next;
}

export function RainfallDetailPanel({
  stationRainfall,
  localForecast,
}: {
  stationRainfall: WeatherSectionState<StationRainfallResponse>;
  localForecast: WeatherSectionState<LocalForecast>;
}) {
  const [editorOpen, setEditorOpen] = useState(false);

  const regionalData =
    stationRainfall.status === "ready" || stationRainfall.status === "stale"
      ? stationRainfall.data
      : null;

  const rawReadings = regionalData?.hourlyRainfall ?? [];
  const readings = useMemo(
    () => rawReadings.map((r) => ({
      automaticWeatherStation: r.automaticWeatherStation,
      automaticWeatherStationID: r.automaticWeatherStationID,
      value: rainfallMm(r.value),
    })),
    [rawReadings],
  );

  const allItems = useMemo(() => buildRainfallStationItems(readings), [readings]);

  const [hiddenStationIds, setHiddenStationIds] = useState<string[]>(() => {
    const stored = getCookie(HIDDEN_RAINFALL_COOKIE);
    if (stored) {
      try {
        const parsed = JSON.parse(stored);
        if (Array.isArray(parsed)) return parsed.filter((item): item is string => typeof item === "string");
      } catch { /* ignore */ }
    }
    return [];
  });

  const [regionOrder, setRegionOrder] = useState<TemperatureRegionId[]>(() => {
    const stored = getCookie(REGION_ORDER_COOKIE);
    if (stored) {
      try {
        const parsed = JSON.parse(stored);
        return normalizeRainfallRegionOrder(Array.isArray(parsed) ? parsed : null);
      } catch { /* ignore */ }
    }
    return [...rainfallDefaultRegionOrder];
  });

  useEffect(() => {
    setCookie(HIDDEN_RAINFALL_COOKIE, JSON.stringify(hiddenStationIds));
  }, [hiddenStationIds]);

  useEffect(() => {
    setCookie(REGION_ORDER_COOKIE, JSON.stringify(regionOrder));
  }, [regionOrder]);

  const hiddenSet = useMemo(() => new Set(hiddenStationIds), [hiddenStationIds]);
  const activeItems = useMemo(
    () => allItems.filter((item) => !hiddenSet.has(item.id)),
    [hiddenSet, allItems],
  );
  const inactiveItems = useMemo(
    () => allItems.filter((item) => hiddenSet.has(item.id)),
    [hiddenSet, allItems],
  );

  const isLoading =
    stationRainfall.status === "loading" || stationRainfall.status === "retrying";
  const updatedAt =
    stationRainfall.status === "ready" || stationRainfall.status === "stale"
      ? stationRainfall.sourceUpdatedAt ?? stationRainfall.fetchedAt
      : null;

  return (
    <div className="rw-panel">
      {forecastSection(localForecast)}
      <div className="rw-section">
        <div className="rw-section-header">
          <h3 className="rw-section-heading">Station Rainfall (past hour)</h3>
        </div>
        {readings.length === 0 && isLoading && (
          <p className="rw-unavailable">Loading rainfall data...</p>
        )}
        {readings.length === 0 && !isLoading && (
          <p className="rw-unavailable">Unavailable</p>
        )}
        {readings.length > 0 && (
          <>
            <div className="temperature-map-heading">
              <p className="temperature-subsection-meta">
                <i className="temperature-map-legend-station" />
                <span>{countItems(activeItems)} stations</span>
                {updatedAt && (
                  <span>Last Updated: {formatTime(updatedAt)}</span>
                )}
              </p>
              <button className="station-editor-trigger" onClick={() => setEditorOpen(true)}>
                Edit
              </button>
            </div>
            <RainfallRegionGrid items={activeItems} regionOrder={regionOrder} />
          </>
        )}
      </div>

      {editorOpen && typeof document !== "undefined" && createPortal(
        <RainfallStationEditor
          activeItems={activeItems}
          inactiveItems={inactiveItems}
          regionOrder={regionOrder}
          onMoveRegion={(regionId, direction) =>
            setRegionOrder((current) => moveRegion(current, regionId, direction))
          }
          onHide={(itemId) =>
            setHiddenStationIds((current) => current.includes(itemId) ? current : [...current, itemId])
          }
          onShow={(itemId) =>
            setHiddenStationIds((current) => current.filter((candidate) => candidate !== itemId))
          }
          onClose={() => setEditorOpen(false)}
        />,
        document.body,
      )}
    </div>
  );
}

function RainfallStationEditor({
  activeItems,
  inactiveItems,
  regionOrder,
  onMoveRegion,
  onHide,
  onShow,
  onClose,
}: {
  activeItems: RainfallStationItem[];
  inactiveItems: RainfallStationItem[];
  regionOrder: readonly TemperatureRegionId[];
  onMoveRegion: (regionId: TemperatureRegionId, direction: -1 | 1) => void;
  onHide: (itemId: string) => void;
  onShow: (itemId: string) => void;
  onClose: () => void;
}) {
  const activeGroups = groupRainfallStations(activeItems, regionOrder);
  const inactiveGroups = groupRainfallStations(inactiveItems, regionOrder);

  return (
    <div className="station-editor-overlay" onClick={onClose}>
      <div className="station-editor" onClick={(e) => e.stopPropagation()}>
        <div className="station-editor-header">
          <h4 className="station-editor-title">Rainfall station selector</h4>
          <button className="station-editor-done" onClick={onClose}>
            Done
          </button>
        </div>
        <div className="station-editor-region-order">
          <p className="station-editor-column-title">Region order</p>
          <div className="station-editor-region-order-list">
            {regionOrder.map((regionId, index) => {
              const label =
                ({ "hong-kong-island": "Hong Kong Island", kowloon: "Kowloon", "new-territories-east": "New Territories East", "new-territories-west": "New Territories West", "outlying-islands": "Outlying Islands" } as Record<TemperatureRegionId, string>)[regionId] ?? regionId;
              return (
                <div key={regionId} className="station-editor-region-order-item">
                  <span className="station-editor-name">{label}</span>
                  <div className="station-editor-region-order-controls">
                    <button
                      className="station-editor-order-button"
                      disabled={index === 0}
                      onClick={() => onMoveRegion(regionId, -1)}
                      type="button"
                      aria-label={`Move ${label} up`}
                    >
                      <span className="station-editor-order-chevron station-editor-order-chevron-up" aria-hidden="true" />
                    </button>
                    <button
                      className="station-editor-order-button"
                      disabled={index === regionOrder.length - 1}
                      onClick={() => onMoveRegion(regionId, 1)}
                      type="button"
                      aria-label={`Move ${label} down`}
                    >
                      <span className="station-editor-order-chevron station-editor-order-chevron-down" aria-hidden="true" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
        <div className="station-editor-columns">
          <div className="station-editor-column">
            <p className="station-editor-column-title">
              Active
              <span className="station-editor-count">{activeItems.length}</span>
            </p>
            <div className="station-editor-list">
              {activeGroups.length === 0 ? (
                <p className="station-editor-empty">No active stations</p>
              ) : (
                activeGroups.map((group) => (
                  <div key={group.id} className="station-editor-region-group">
                    <p className="station-editor-region-title">{group.label}</p>
                    <div className="station-editor-column-list">
                      {group.items.map((item) => (
                        <label key={item.id} className="station-editor-item">
                          <span className="station-editor-name">{item.label}</span>
                          <button
                            className="station-editor-remove"
                            onClick={() => onHide(item.id)}
                            type="button"
                          >
                            Hide
                          </button>
                        </label>
                      ))}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
          <div className="station-editor-column">
            <p className="station-editor-column-title">
              Inactive
              <span className="station-editor-count">{inactiveItems.length}</span>
            </p>
            <div className="station-editor-list">
              {inactiveGroups.length === 0 ? (
                <p className="station-editor-empty">All stations active</p>
              ) : (
                inactiveGroups.map((group) => (
                  <div key={group.id} className="station-editor-region-group">
                    <p className="station-editor-region-title">{group.label}</p>
                    <div className="station-editor-column-list">
                      {group.items.map((item) => (
                        <label key={item.id} className="station-editor-item">
                          <span className="station-editor-name">{item.label}</span>
                          <button
                            className="station-editor-add"
                            onClick={() => onShow(item.id)}
                            type="button"
                          >
                            Show
                          </button>
                        </label>
                      ))}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
