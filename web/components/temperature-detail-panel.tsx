"use client";

import { useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { TemperatureOverviewMap } from "@/components/hong-kong-weather-map";
import { temperatureDisplayName } from "@/lib/weather/view-models";
import {
  buildTemperatureSensorItems,
  defaultTemperatureRegionOrder,
  groupTemperatureSensors,
  normalizeTemperatureRegionOrder,
  stationSensorId,
  temperatureRegions,
  type TemperatureRegionId,
  type TemperatureSensorItem,
} from "@/lib/weather/temperature-regions";
import type { WeatherSectionState } from "@/lib/weather/state";
import type {
  LamppostReading,
  PlaceValue,
  TemperatureReading,
  WindReading,
} from "@/lib/weather/types";

const ACTIVE_SENSORS_COOKIE_NAME = "hkw-active-stations";
const HIDDEN_SENSORS_COOKIE_NAME = "hkw-hidden-temperature-sensors";
const REGION_ORDER_COOKIE_NAME = "hkw-temperature-region-order";

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(`(?:^|; )${name}=([^;]*)`);
  return match ? decodeURIComponent(match[1]) : null;
}

function setCookie(name: string, value: string) {
  document.cookie = `${name}=${encodeURIComponent(value)}; path=/; max-age=31536000; SameSite=Lax`;
}

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString("en-HK", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Hong_Kong",
  });
}

function loadedData<Data>(section: WeatherSectionState<Data>): Data | null {
  return section.status === "ready" || section.status === "stale"
    ? section.data
    : null;
}

function isStoredSensorId(value: string) {
  return value.startsWith("station:") || value.startsWith("lamppost:");
}

function readStoredHiddenSensorIds({
  availableItems,
  lamppostItems,
}: {
  availableItems: TemperatureSensorItem[];
  lamppostItems: TemperatureSensorItem[];
}) {
  const storedHidden = getCookie(HIDDEN_SENSORS_COOKIE_NAME);
  if (storedHidden) {
    try {
      const parsed = JSON.parse(storedHidden);
      if (!Array.isArray(parsed)) return [];
      return parsed.filter((item): item is string => typeof item === "string");
    } catch {
      return [];
    }
  }

  const stored = getCookie(ACTIVE_SENSORS_COOKIE_NAME);
  if (!stored) return [];

  try {
    const parsed = JSON.parse(stored);
    if (!Array.isArray(parsed)) return [];

    const values = parsed.filter((item): item is string => typeof item === "string");
    if (values.every(isStoredSensorId)) return [];

    const migratedStationIds = values.map((station) => stationSensorId(station));
    const activeIds = new Set([...migratedStationIds, ...lamppostItems.map((item) => item.id)]);
    return availableItems
      .map((item) => item.id)
      .filter((itemId) => !activeIds.has(itemId));
  } catch {
    return [];
  }
}

function readStoredRegionOrder() {
  const stored = getCookie(REGION_ORDER_COOKIE_NAME);
  if (!stored) return [...defaultTemperatureRegionOrder];

  try {
    const parsed = JSON.parse(stored);
    return normalizeTemperatureRegionOrder(Array.isArray(parsed) ? parsed : null);
  } catch {
    return [...defaultTemperatureRegionOrder];
  }
}

function countItems(items: TemperatureSensorItem[], kind: TemperatureSensorItem["kind"]) {
  return items.filter((item) => item.kind === kind).length;
}

function moveRegion(regionOrder: readonly TemperatureRegionId[], regionId: TemperatureRegionId, direction: -1 | 1) {
  const index = regionOrder.indexOf(regionId);
  const nextIndex = index + direction;
  if (index === -1 || nextIndex < 0 || nextIndex >= regionOrder.length) return [...regionOrder];

  const next = [...regionOrder];
  const [moved] = next.splice(index, 1);
  next.splice(nextIndex, 0, moved);
  return next;
}

function firstLamppostLocation(label: string) {
  return label.split("/")[0]?.trim() ?? label;
}

function WindArrow({ direction }: { direction: string | null }) {
  const degMap: Record<string, number> = {
    North: 0,
    "North Northeast": 22.5,
    Northeast: 45,
    "East Northeast": 67.5,
    East: 90,
    "East Southeast": 112.5,
    Southeast: 135,
    "South Southeast": 157.5,
    South: 180,
    "South Southwest": 202.5,
    Southwest: 225,
    "West Southwest": 247.5,
    West: 270,
    "West Northwest": 292.5,
    Northwest: 315,
    "North Northwest": 337.5,
  };
  const deg = direction ? degMap[direction] ?? 0 : 0;

  return (
    <svg
      width="12"
      height="12"
      viewBox="0 0 12 12"
      fill="none"
      className="temperature-wind-arrow"
      aria-label={`Wind direction ${direction ?? "unknown"}`}
      style={{ transform: `rotate(${deg}deg)` }}
    >
      <path d="M6 1.5L10.5 10.5L6 8.5L1.5 10.5L6 1.5Z" fill="currentColor" />
    </svg>
  );
}

function TemperatureSensorCard({ item, windDirection, windSpeedKmh }: { item: TemperatureSensorItem; windDirection: string | null; windSpeedKmh: number | null }) {
  const sensorLabel = item.kind === "lamppost" ? firstLamppostLocation(item.label) : temperatureDisplayName(item.label);
  const hasWind = windDirection || (windSpeedKmh !== null);

  return (
    <div className="temperature-station-row" data-kind={item.kind}>
      <span className="temperature-sensor-kind">{item.kind === "station" ? "Station" : "Lamppost"}</span>
      <span className="temperature-station-name">{sensorLabel}</span>
      <span className="temperature-station-value-row">
        <span className="temperature-station-value">
          {item.temperature !== null ? (
            <>
              {Number(item.temperature).toFixed(1)}
              <span aria-hidden="true">°</span>
              <span className="sr-only"> degrees Celsius</span>
            </>
          ) : (
            <span className="weather-value-unavailable" aria-label="Unavailable">
              --
            </span>
          )}
        </span>
        {hasWind && (
          <span className="temperature-station-wind">
            <WindArrow direction={windDirection} />
            <span className="temperature-wind-speed">
              {windSpeedKmh !== null ? windSpeedKmh : "--"}
            </span>
          </span>
        )}
      </span>
    </div>
  );
}

function TemperatureRegionGrid({
  items,
  regionOrder,
  windByStation,
  heading,
  stationCount,
  stationUpdateTime,
  lamppostCount,
  lamppostUpdateTime,
  onEdit,
}: {
  items: TemperatureSensorItem[];
  regionOrder: readonly TemperatureRegionId[];
  windByStation: Map<string, WindReading>;
  heading?: React.ReactNode;
  stationCount: number;
  stationUpdateTime: string | null;
  lamppostCount: number;
  lamppostUpdateTime: string | null;
  onEdit: () => void;
}) {
  const groups = groupTemperatureSensors(items, regionOrder);

  return (
    <div className="temperature-region-list">
      {heading}
      <div className="temperature-map-heading">
        <div>
          <p className="temperature-subsection-meta">
            <i className="temperature-map-legend-station" />
            <span>{stationCount} stations</span>
            <span>Last Updated: {stationUpdateTime ? formatTime(stationUpdateTime) : "--:--"}</span>
            <span className="temperature-subsection-meta-dot">·</span>
            <i className="temperature-map-legend-lamppost" />
            <span>{lamppostCount} lampposts</span>
            <span>Last Updated: {lamppostUpdateTime ? formatTime(lamppostUpdateTime) : "--:--"}</span>
          </p>
        </div>
        <div className="temperature-map-heading-row">
          <button className="station-editor-trigger" onClick={onEdit}>
            Edit
          </button>
        </div>
      </div>
      {groups.map((group) => (
        <section key={group.id} className="temperature-region-group">
          <div className="temperature-region-header">
            <h3 className="temperature-subsection-title">{group.label}</h3>
            <span className="temperature-region-count">{group.items.length}</span>
          </div>
          <div className="temperature-station-list">
            {group.items.map((item) => {
              const stationWind = windByStation.get(item.label) ?? null;
              const windDir = item.kind === "lamppost" ? item.windDirection : stationWind?.meanWindDirection ?? null;
              const windSpeed = item.kind === "lamppost" ? item.windSpeedKmh : stationWind?.meanWindSpeedKmh ?? null;
              return (
                <TemperatureSensorCard key={item.id} item={item} windDirection={windDir} windSpeedKmh={windSpeed} />
              );
            })}
          </div>
        </section>
      ))}
      <p className="temperature-info">
        Station temperature is measured by electronic thermometers at automatic weather stations and smart lampposts across Hong Kong.
      </p>
    </div>
  );
}

export function TemperatureDetailPanel({
  currentTemperatures,
  regionalTemperature,
  lampposts,
  regionalWind,
}: {
  currentTemperatures: readonly PlaceValue<"C">[];
  regionalTemperature: WeatherSectionState<TemperatureReading[]>;
  lampposts: WeatherSectionState<LamppostReading[]>;
  regionalWind: WeatherSectionState<WindReading[]>;
}) {
  const [editorOpen, setEditorOpen] = useState(false);

  const regionalReadings = loadedData(regionalTemperature);
  const lamppostReadings = loadedData(lampposts);
  const windReadings = loadedData(regionalWind);
  const isLoading =
    regionalTemperature.status === "loading" ||
    regionalTemperature.status === "retrying" ||
    lampposts.status === "loading" ||
    lampposts.status === "retrying";

  const windByStation = useMemo(() => {
    const map = new Map<string, WindReading>();
    if (windReadings) {
      for (const reading of windReadings) {
        map.set(reading.station, reading);
      }
    }
    return map;
  }, [windReadings]);

  const allItems = useMemo(
    () => buildTemperatureSensorItems({
      regionalReadings: regionalReadings ?? [],
      lamppostReadings: lamppostReadings ?? [],
      includeAllStations: true,
    }),
    [regionalReadings, lamppostReadings],
  );
  const lamppostItems = useMemo(
    () => allItems.filter((item) => item.kind === "lamppost"),
    [allItems],
  );
  const [hiddenSensorIds, setHiddenSensorIds] = useState<string[]>(() =>
    readStoredHiddenSensorIds({ availableItems: allItems, lamppostItems }),
  );
  const [regionOrder, setRegionOrder] = useState<TemperatureRegionId[]>(() =>
    readStoredRegionOrder(),
  );

  useEffect(() => {
    setCookie(HIDDEN_SENSORS_COOKIE_NAME, JSON.stringify(hiddenSensorIds));
  }, [hiddenSensorIds]);

  useEffect(() => {
    setCookie(REGION_ORDER_COOKIE_NAME, JSON.stringify(regionOrder));
  }, [regionOrder]);

  const hiddenSensorSet = useMemo(() => new Set(hiddenSensorIds), [hiddenSensorIds]);
  const activeItems = useMemo(
    () => allItems.filter((item) => !hiddenSensorSet.has(item.id)),
    [hiddenSensorSet, allItems],
  );
  const inactiveItems = useMemo(
    () => allItems.filter((item) => hiddenSensorSet.has(item.id)),
    [hiddenSensorSet, allItems],
  );

  const stationUpdateTime =
    regionalTemperature.status === "ready" || regionalTemperature.status === "stale"
      ? regionalTemperature.sourceUpdatedAt
      : null;
  const lamppostUpdateTime =
    lampposts.status === "ready" || lampposts.status === "stale"
      ? lampposts.sourceUpdatedAt
      : null;

  return (
    <div className="temperature-detail-panel">
      <TemperatureOverviewMap readings={currentTemperatures} />

      {regionalReadings || lamppostReadings ? (
        <TemperatureRegionGrid
          items={activeItems}
          regionOrder={regionOrder}
          windByStation={windByStation}
          heading={
            <div className="rw-section-header">
              <h3 className="rw-section-heading">Station &amp; Lamppost Temperature (past hour)</h3>
            </div>
          }
          stationCount={countItems(activeItems, "station")}
          stationUpdateTime={stationUpdateTime}
          lamppostCount={countItems(activeItems, "lamppost")}
          lamppostUpdateTime={lamppostUpdateTime}
          onEdit={() => setEditorOpen(true)}
        />
      ) : (
        <p className={isLoading ? "temperature-loading" : "temperature-unavailable"}>
          {isLoading ? "Loading station temperatures..." : "Station temperature data is unavailable"}
        </p>
      )}

      {editorOpen && typeof document !== "undefined" && createPortal(
        <StationEditor
          activeItems={activeItems}
          inactiveItems={inactiveItems}
          regionOrder={regionOrder}
          onMoveRegion={(regionId, direction) =>
            setRegionOrder((current) => moveRegion(current, regionId, direction))
          }
          onHide={(itemId) =>
            setHiddenSensorIds((current) => current.includes(itemId) ? current : [...current, itemId])
          }
          onShow={(itemId) =>
            setHiddenSensorIds((current) => current.filter((candidate) => candidate !== itemId))
          }
          onClose={() => setEditorOpen(false)}
        />,
        document.body
      )}
    </div>
  );
}

function StationEditor({
  activeItems,
  inactiveItems,
  regionOrder,
  onMoveRegion,
  onHide,
  onShow,
  onClose,
}: {
  activeItems: TemperatureSensorItem[];
  inactiveItems: TemperatureSensorItem[];
  regionOrder: readonly TemperatureRegionId[];
  onMoveRegion: (regionId: TemperatureRegionId, direction: -1 | 1) => void;
  onHide: (itemId: string) => void;
  onShow: (itemId: string) => void;
  onClose: () => void;
}) {
  const activeGroups = groupTemperatureSensors(activeItems, regionOrder);
  const inactiveGroups = groupTemperatureSensors(inactiveItems, regionOrder);

  return (
    <div className="station-editor-overlay" onClick={onClose}>
      <div className="station-editor" onClick={(e) => e.stopPropagation()}>
        <div className="station-editor-header">
          <h4 className="station-editor-title">Temperature selector</h4>
          <button className="station-editor-done" onClick={onClose}>
            Done
          </button>
        </div>
        <div className="station-editor-region-order">
          <p className="station-editor-column-title">Region order</p>
          <div className="station-editor-region-order-list">
            {regionOrder.map((regionId, index) => {
              const region = temperatureRegions.find((entry) => entry.id === regionId);
              if (!region) return null;

              return (
                <div
                  key={region.id}
                  className="station-editor-region-order-item"
                >
                  <span className="station-editor-name">{region.label}</span>
                  <div className="station-editor-region-order-controls">
                    <button
                      className="station-editor-order-button"
                      disabled={index === 0}
                      onClick={() => onMoveRegion(region.id, -1)}
                      type="button"
                      aria-label={`Move ${region.label} up`}
                    >
                      <span className="station-editor-order-chevron station-editor-order-chevron-up" aria-hidden="true" />
                    </button>
                    <button
                      className="station-editor-order-button"
                      disabled={index === regionOrder.length - 1}
                      onClick={() => onMoveRegion(region.id, 1)}
                      type="button"
                      aria-label={`Move ${region.label} down`}
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
                <p className="station-editor-empty">No active sensors</p>
              ) : (
                activeGroups.map((group) => (
                  <div key={group.id} className="station-editor-region-group">
                    <p className="station-editor-region-title">{group.label}</p>
                    <div className="station-editor-column-list">
                      {group.items.map((item) => (
                        <label key={item.id} className="station-editor-item">
                          <span className="station-editor-item-kind">{item.kind}</span>
                          <span className="station-editor-name">{item.kind === "lamppost" ? firstLamppostLocation(item.label) : temperatureDisplayName(item.label)}</span>
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
                <p className="station-editor-empty">All sensors active</p>
              ) : (
                inactiveGroups.map((group) => (
                  <div key={group.id} className="station-editor-region-group">
                    <p className="station-editor-region-title">{group.label}</p>
                    <div className="station-editor-column-list">
                      {group.items.map((item) => (
                        <label key={item.id} className="station-editor-item">
                          <span className="station-editor-item-kind">{item.kind}</span>
                          <span className="station-editor-name">{item.kind === "lamppost" ? firstLamppostLocation(item.label) : temperatureDisplayName(item.label)}</span>
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
