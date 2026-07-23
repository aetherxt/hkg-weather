"use client";

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
} from "react";

import { regionalStationLocations } from "@/lib/weather/station-locations";
import { weatherClient } from "@/lib/weather/client";
import type {
  DistrictRainfallReading,
  PlaceValue,
  RadarMetadata,
} from "@/lib/weather/types";

const MAP = {
  width: 700,
  height: 370,
  tileSize: 256,
  initialZoom: 10,
  minZoom: 10,
  maxZoom: 13.5,
  centerLongitude: 114.135,
  centerLatitude: 22.375,
};

const HONG_KONG_BOUNDS = {
  west: 113.82,
  east: 114.45,
  north: 22.55,
  south: 22.16,
};

const INITIAL_VIEW: MapView = {
  longitude: MAP.centerLongitude,
  latitude: MAP.centerLatitude,
  zoom: MAP.initialZoom,
};

const stationAliases: Readonly<Record<string, string>> = {
  "Hong Kong Observatory": "HK Observatory",
  "Hong Kong Park": "HK Park",
};

const labelOffsets: Readonly<Record<string, readonly [number, number]>> = {
  "HK Observatory": [-13, 4],
  "King's Park": [14, -7],
  "HK Park": [-13, 7],
  "Happy Valley": [14, 6],
  "Kowloon City": [8, -8],
  "Kwun Tong": [11, 6],
  "Sham Shui Po": [-13, -5],
  "Wong Tai Sin": [11, -5],
  "Tsuen Wan Shing Mun Valley": [10, 7],
  "Tsuen Wan Ho Koon": [-13, -7],
  "Tai Po": [-9, 6],
  "Tai Mei Tuk": [11, -3],
};

const districtLocations: Readonly<
  Record<string, readonly [longitude: number, latitude: number]>
> = {
  "Central & Western District": [114.1455, 22.2868],
  "Eastern District": [114.225, 22.283],
  "Islands District": [113.946, 22.281],
  "Kowloon City": [114.188, 22.328],
  "Kwai Tsing": [114.105, 22.354],
  "Kwun Tong": [114.226, 22.31],
  "North District": [114.148, 22.501],
  "Sai Kung": [114.264, 22.381],
  "Sha Tin": [114.194, 22.387],
  "Sham Shui Po": [114.143, 22.331],
  "Southern District": [114.16, 22.247],
  "Tai Po": [114.172, 22.45],
  "Tsuen Wan": [114.117, 22.373],
  "Tuen Mun": [113.977, 22.391],
  "Wan Chai": [114.175, 22.276],
  "Wong Tai Sin": [114.203, 22.342],
  "Yau Tsim Mong": [114.169, 22.307],
  "Yuen Long": [114.032, 22.445],
};

interface MapView {
  longitude: number;
  latitude: number;
  zoom: number;
}

interface DragState {
  pointerId: number;
  startX: number;
  startY: number;
  centerX: number;
  centerY: number;
  coordinateScale: number;
  zoom: number;
}

interface PointerPosition {
  x: number;
  y: number;
}

interface PinchState {
  startDistance: number;
  startZoom: number;
}

interface HongKongMapReading {
  id: string;
  label: string;
  value: number;
  longitude: number;
  latitude: number;
  offsetX?: number;
  offsetY?: number;
}

interface WeatherMapMarker {
  id: string;
  label: string;
  value: number;
  x: number;
  y: number;
}

interface WeatherMapMarkerGroup {
  id: string;
  x: number;
  y: number;
  value: number;
  markers: WeatherMapMarker[];
}

function project(longitude: number, latitude: number) {
  const latitudeRadians = (latitude * Math.PI) / 180;
  return {
    x: (longitude + 180) / 360,
    y:
      (1 -
        Math.log(
          Math.tan(latitudeRadians) + 1 / Math.cos(latitudeRadians),
        ) /
          Math.PI) /
      2,
  };
}

function unproject(x: number, y: number) {
  const mercatorY = Math.PI * (1 - 2 * y);
  return {
    longitude: x * 360 - 180,
    latitude:
      (Math.atan(Math.sinh(mercatorY)) * 180) /
      Math.PI,
  };
}

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(maximum, Math.max(minimum, value));
}

function clampView(view: MapView): MapView {
  const zoom = clamp(view.zoom, MAP.minZoom, MAP.maxZoom);
  const pixelsPerWorld = MAP.tileSize * 2 ** zoom;
  const halfWidth = MAP.width / (2 * pixelsPerWorld);
  const halfHeight = MAP.height / (2 * pixelsPerWorld);
  const northwest = project(
    HONG_KONG_BOUNDS.west,
    HONG_KONG_BOUNDS.north,
  );
  const southeast = project(
    HONG_KONG_BOUNDS.east,
    HONG_KONG_BOUNDS.south,
  );
  const center = project(view.longitude, view.latitude);
  const minimumX = northwest.x + halfWidth;
  const maximumX = southeast.x - halfWidth;
  const minimumY = northwest.y + halfHeight;
  const maximumY = southeast.y - halfHeight;
  const x =
    minimumX <= maximumX
      ? clamp(center.x, minimumX, maximumX)
      : (northwest.x + southeast.x) / 2;
  const y =
    minimumY <= maximumY
      ? clamp(center.y, minimumY, maximumY)
      : (northwest.y + southeast.y) / 2;
  const geographic = unproject(x, y);

  return {
    longitude: geographic.longitude,
    latitude: geographic.latitude,
    zoom,
  };
}

function temperatureColor(temperature: number) {
  const normalized = clamp(temperature / 40, 0, 1);
  const hue = 220 * (1 - normalized);
  return `hsl(${hue.toFixed(0)} 72% 42%)`;
}

function rainfallColor(rainfall: number) {
  const normalized = clamp(rainfall / 50, 0, 1);
  const lightness = 48 - normalized * 18;
  return `hsl(210 78% ${lightness.toFixed(0)}%)`;
}

function formatTemperature(value: number) {
  return `${value.toFixed(0)}°`;
}

function formatRainfall(value: number) {
  const digits = value > 0 && value < 10 && !Number.isInteger(value) ? 1 : 0;
  return `${value.toFixed(digits)} mm`;
}

function formatRadarUpdatedAt(value: string) {
  return new Date(value).toLocaleTimeString("en-HK", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Hong_Kong",
  });
}

function groupOverlappingMarkers(
  markers: WeatherMapMarker[],
): WeatherMapMarkerGroup[] {
  const visited = new Set<number>();
  const groups: WeatherMapMarkerGroup[] = [];

  markers.forEach((marker, markerIndex) => {
    if (visited.has(markerIndex)) return;

    const pending = [markerIndex];
    const members: WeatherMapMarker[] = [];
    visited.add(markerIndex);

    while (pending.length > 0) {
      const currentIndex = pending.pop();
      if (currentIndex === undefined) break;
      const current = markers[currentIndex];
      members.push(current);

      markers.forEach((candidate, candidateIndex) => {
        if (
          visited.has(candidateIndex) ||
          Math.abs(candidate.x - current.x) >= 34 ||
          Math.abs(candidate.y - current.y) >= 22
        ) {
          return;
        }

        visited.add(candidateIndex);
        pending.push(candidateIndex);
      });
    }

    groups.push({
      id: members.map((member) => member.id).sort().join("|"),
      x:
        members.reduce((total, member) => total + member.x, 0) /
        members.length,
      y:
        members.reduce((total, member) => total + member.y, 0) /
        members.length,
      value:
        members.reduce((total, member) => total + member.value, 0) /
        members.length,
      markers: members,
    });
  });

  return groups;
}

function HongKongWeatherMap({
  title,
  metricLabel,
  readings,
  formatValue,
  colorForValue,
  radar,
}: {
  title: string;
  metricLabel: string;
  readings: readonly HongKongMapReading[];
  formatValue: (value: number) => string;
  colorForValue: (value: number) => string;
  radar?: RadarMetadata | null;
}) {
  const [view, setView] = useState<MapView>(() => clampView(INITIAL_VIEW));
  const [dragging, setDragging] = useState(false);
  const dragState = useRef<DragState | null>(null);
  const pinchState = useRef<PinchState | null>(null);
  const pointers = useRef(new Map<number, PointerPosition>());
  const viewportRef = useRef<HTMLDivElement>(null);

  const geometry = useMemo(() => {
    const tileZoom = Math.floor(view.zoom);
    const renderScale = 2 ** (view.zoom - tileZoom);
    const tileWorldSize = MAP.tileSize * 2 ** tileZoom;
    const center = project(view.longitude, view.latitude);
    const centerX = center.x * tileWorldSize;
    const centerY = center.y * tileWorldSize;
    const viewportLeft = centerX - MAP.width / (2 * renderScale);
    const viewportTop = centerY - MAP.height / (2 * renderScale);
    const viewportWorldWidth = MAP.width / renderScale;
    const viewportWorldHeight = MAP.height / renderScale;
    const firstColumn = Math.floor(viewportLeft / MAP.tileSize);
    const lastColumn = Math.floor(
      (viewportLeft + viewportWorldWidth) / MAP.tileSize,
    );
    const firstRow = Math.floor(viewportTop / MAP.tileSize);
    const lastRow = Math.floor(
      (viewportTop + viewportWorldHeight) / MAP.tileSize,
    );
    const tiles: Array<{
      x: number;
      y: number;
      screenX: number;
      screenY: number;
    }> = [];

    for (let tileY = firstRow; tileY <= lastRow; tileY += 1) {
      for (let tileX = firstColumn; tileX <= lastColumn; tileX += 1) {
        tiles.push({
          x: tileX,
          y: tileY,
          screenX: (tileX * MAP.tileSize - viewportLeft) * renderScale,
          screenY: (tileY * MAP.tileSize - viewportTop) * renderScale,
        });
      }
    }

    return {
      renderScale,
      tileZoom,
      tiles,
    };
  }, [view]);

  const markers = useMemo(() => {
    const center = project(view.longitude, view.latitude);
    const pixelsPerWorld = MAP.tileSize * 2 ** view.zoom;

    return readings.flatMap((reading) => {
      const location = project(reading.longitude, reading.latitude);

      return [
        {
          id: reading.id,
          label: reading.label,
          value: reading.value,
          x:
            MAP.width / 2 +
            (location.x - center.x) * pixelsPerWorld +
            (reading.offsetX ?? 0),
          y:
            MAP.height / 2 +
            (location.y - center.y) * pixelsPerWorld +
            (reading.offsetY ?? 0),
        },
      ];
    });
  }, [readings, view]);

  const markerGroups = useMemo(
    () => groupOverlappingMarkers(markers),
    [markers],
  );

  const radarGeometry = useMemo(() => {
    if (!radar) return null;
    const center = project(view.longitude, view.latitude);
    const pixelsPerWorld = MAP.tileSize * 2 ** view.zoom;
    const northwest = project(radar.bounds.west, radar.bounds.north);
    const southeast = project(radar.bounds.east, radar.bounds.south);

    return {
      x: MAP.width / 2 + (northwest.x - center.x) * pixelsPerWorld,
      y: MAP.height / 2 + (northwest.y - center.y) * pixelsPerWorld,
      width: (southeast.x - northwest.x) * pixelsPerWorld,
      height: (southeast.y - northwest.y) * pixelsPerWorld,
    };
  }, [radar, view]);

  function zoomBy(amount: number) {
    setView((current) =>
      clampView({
        ...current,
        zoom: current.zoom + amount,
      }),
    );
  }

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;

    function handleWheel(event: globalThis.WheelEvent) {
      event.preventDefault();
      event.stopPropagation();
      if (event.deltaY === 0) return;

      setView((current) =>
        clampView({
          ...current,
          zoom: current.zoom + (event.deltaY < 0 ? 0.25 : -0.25),
        }),
      );
    }

    viewport.addEventListener("wheel", handleWheel, { passive: false });
    return () => viewport.removeEventListener("wheel", handleWheel);
  }, []);

  function panByPixels(deltaX: number, deltaY: number) {
    setView((current) => {
      const center = project(current.longitude, current.latitude);
      const pixelsPerWorld = MAP.tileSize * 2 ** current.zoom;
      const geographic = unproject(
        center.x + deltaX / pixelsPerWorld,
        center.y + deltaY / pixelsPerWorld,
      );
      return clampView({
        ...current,
        ...geographic,
      });
    });
  }

  function handlePointerDown(event: PointerEvent<SVGSVGElement>) {
    if (event.button !== 0) return;
    pointers.current.set(event.pointerId, {
      x: event.clientX,
      y: event.clientY,
    });
    event.currentTarget.setPointerCapture(event.pointerId);

    if (pointers.current.size >= 2) {
      const [first, second] = Array.from(pointers.current.values());
      pinchState.current = {
        startDistance: Math.max(
          1,
          Math.hypot(second.x - first.x, second.y - first.y),
        ),
        startZoom: view.zoom,
      };
      dragState.current = null;
      setDragging(true);
      event.preventDefault();
      return;
    }

    const center = project(view.longitude, view.latitude);
    dragState.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      centerX: center.x,
      centerY: center.y,
      coordinateScale:
        MAP.width / event.currentTarget.getBoundingClientRect().width,
      zoom: view.zoom,
    };
    setDragging(true);
  }

  function handlePointerMove(event: PointerEvent<SVGSVGElement>) {
    if (pointers.current.has(event.pointerId)) {
      pointers.current.set(event.pointerId, {
        x: event.clientX,
        y: event.clientY,
      });
    }

    if (pointers.current.size >= 2) {
      const pinch = pinchState.current;
      if (!pinch) return;
      const [first, second] = Array.from(pointers.current.values());
      const distance = Math.max(
        1,
        Math.hypot(second.x - first.x, second.y - first.y),
      );

      setView((current) =>
        clampView({
          ...current,
          zoom:
            pinch.startZoom +
            Math.log2(distance / pinch.startDistance),
        }),
      );
      event.preventDefault();
      return;
    }

    const drag = dragState.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const pixelsPerWorld = MAP.tileSize * 2 ** drag.zoom;
    const geographic = unproject(
      drag.centerX -
        ((event.clientX - drag.startX) * drag.coordinateScale) /
          pixelsPerWorld,
      drag.centerY -
        ((event.clientY - drag.startY) * drag.coordinateScale) /
          pixelsPerWorld,
    );

    setView(
      clampView({
        ...geographic,
        zoom: drag.zoom,
      }),
    );
  }

  function endPointerInteraction(event: PointerEvent<SVGSVGElement>) {
    pointers.current.delete(event.pointerId);
    pinchState.current = null;
    if (dragState.current?.pointerId === event.pointerId) {
      dragState.current = null;
    }
    setDragging(dragState.current !== null);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  function handleKeyDown(event: KeyboardEvent<SVGSVGElement>) {
    const movement = 42;
    if (event.key === "ArrowLeft") panByPixels(-movement, 0);
    else if (event.key === "ArrowRight") panByPixels(movement, 0);
    else if (event.key === "ArrowUp") panByPixels(0, -movement);
    else if (event.key === "ArrowDown") panByPixels(0, movement);
    else if (event.key === "+" || event.key === "=") zoomBy(0.25);
    else if (event.key === "-") zoomBy(-0.25);
    else return;
    event.preventDefault();
  }

  return (
    <section
      className="weather-overview-map"
      aria-labelledby="hong-kong-weather-map-title"
    >
      <div className="rw-section-header">
        <h3
          className="rw-section-heading"
          id="hong-kong-weather-map-title"
        >
          {title}
        </h3>
        {radar ? (
          <span className="rw-updated-at">
            Radar Updated At: {formatRadarUpdatedAt(radar.observedAt)}
          </span>
        ) : null}
      </div>
      <div
        className="weather-overview-map-viewport"
        ref={viewportRef}
      >
        <svg
          className="weather-overview-map-chart"
          data-dragging={dragging ? "true" : undefined}
          viewBox={`0 0 ${MAP.width} ${MAP.height}`}
          role="application"
          tabIndex={0}
          aria-label={`Interactive OpenStreetMap view of ${markers.length} current ${metricLabel} readings in ${markerGroups.length} visible marker groups across Hong Kong. Drag or use arrow keys to pan; scroll or use plus and minus to zoom.`}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={endPointerInteraction}
          onPointerCancel={endPointerInteraction}
          onKeyDown={handleKeyDown}
        >
          <rect className="temperature-map-water" width="700" height="370" />

          <g className="temperature-map-tiles" aria-hidden="true">
            {geometry.tiles.map((tile) => (
              <image
                className="temperature-map-tile"
                href={`https://a.basemaps.cartocdn.com/light_nolabels/${geometry.tileZoom}/${tile.x}/${tile.y}@2x.png`}
                x={tile.screenX}
                y={tile.screenY}
                width={MAP.tileSize * geometry.renderScale}
                height={MAP.tileSize * geometry.renderScale}
                key={`${geometry.tileZoom}-${tile.x}-${tile.y}`}
              />
            ))}
          </g>
          <rect
            className="temperature-map-desaturating-layer"
            width="700"
            height="370"
            aria-hidden="true"
          />
          {radar && radarGeometry ? (
            <g className="weather-map-radar-layer" aria-hidden="true">
              <image
                className="weather-map-radar-overlay"
                href={`${radar.imageUrl}?observedAt=${encodeURIComponent(radar.observedAt)}`}
                x={radarGeometry.x}
                y={radarGeometry.y}
                width={radarGeometry.width}
                height={radarGeometry.height}
                preserveAspectRatio="none"
              />
            </g>
          ) : null}

          <g className="weather-map-marker-layer">
            {markerGroups.map((group) => (
              <text
                className="temperature-map-reading"
                data-grouped={group.markers.length > 1 ? "true" : undefined}
                x={group.x}
                y={group.y}
                fill={colorForValue(group.value)}
                textAnchor="middle"
                key={group.id}
              >
                <title>
                  {group.markers
                    .map(
                      (marker) =>
                        `${marker.label}: ${formatValue(marker.value)}`,
                    )
                    .join("; ")}
                </title>
                {formatValue(group.value)}
              </text>
            ))}
          </g>
        </svg>

        <div className="temperature-map-controls" aria-label="Map zoom controls">
          <button
            type="button"
            aria-label="Zoom in"
            disabled={view.zoom >= MAP.maxZoom}
            onClick={() => zoomBy(0.25)}
          >
            +
          </button>
          <button
            type="button"
            aria-label="Zoom out"
            disabled={view.zoom <= MAP.minZoom}
            onClick={() => zoomBy(-0.25)}
          >
            −
          </button>
          <button
            type="button"
            aria-label="Reset map view"
            title="Reset view"
            onClick={() => setView(clampView(INITIAL_VIEW))}
          >
            <svg
              className="weather-map-reset-icon"
              viewBox="0 0 20 20"
              aria-hidden="true"
            >
              <path d="M7 3H3v4M13 3h4v4M17 13v4h-4M7 17H3v-4" />
              <circle cx="10" cy="10" r="2.25" />
            </svg>
          </button>
        </div>

        <p className="temperature-map-attribution">
          <a
            href="https://www.openstreetmap.org/copyright"
            target="_blank"
            rel="noreferrer"
          >
            © OpenStreetMap
          </a>
          <span aria-hidden="true"> · </span>
          <a
            href="https://carto.com/attributions"
            target="_blank"
            rel="noreferrer"
          >
            © CARTO
          </a>
        </p>
      </div>
    </section>
  );
}

export function TemperatureOverviewMap({
  readings,
}: {
  readings: readonly PlaceValue<"C">[];
}) {
  const mapReadings = useMemo(
    () =>
      readings.flatMap((reading) => {
        const stationName = stationAliases[reading.place] ?? reading.place;
        const coordinates = regionalStationLocations[stationName];
        if (!coordinates) return [];
        const [offsetX, offsetY] = labelOffsets[stationName] ?? [0, 0];

        return [{
          id: reading.place,
          label: reading.place,
          value: reading.value,
          longitude: coordinates[0],
          latitude: coordinates[1],
          offsetX,
          offsetY,
        }];
      }),
    [readings],
  );

  return (
    <HongKongWeatherMap
      title="District Temperature Map"
      metricLabel="temperature"
      readings={mapReadings}
      formatValue={formatTemperature}
      colorForValue={temperatureColor}
    />
  );
}

export function RainfallOverviewMap({
  readings,
}: {
  readings: readonly DistrictRainfallReading[];
}) {
  const [radar, setRadar] = useState<RadarMetadata | null>(null);

  useEffect(() => {
    let active = true;

    weatherClient
      .getRadar()
      .then((response) => {
        if (active) setRadar(response.data);
      })
      .catch(() => {
        if (active) setRadar(null);
      });

    return () => {
      active = false;
    };
  }, []);

  const mapReadings = useMemo(
    () =>
      readings.flatMap((reading) => {
        const coordinates = districtLocations[reading.place];
        if (!coordinates) return [];

        return [{
          id: reading.place,
          label: reading.place,
          value: reading.max,
          longitude: coordinates[0],
          latitude: coordinates[1],
        }];
      }),
    [readings],
  );

  return (
    <HongKongWeatherMap
      title="District Rainfall Map"
      metricLabel="district rainfall"
      readings={mapReadings}
      formatValue={formatRainfall}
      colorForValue={rainfallColor}
      radar={radar}
    />
  );
}
