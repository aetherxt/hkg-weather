"use client";

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
} from "react";

import type { TyphoonModelFrame } from "@/components/typhoon-track-page";
import {
  decodeEarthWeatherRainfall,
  decodeEarthWeatherWind,
  sampleEarthWeatherVector,
  type EarthWeatherScalarGrid,
  type EarthWeatherVectorGrid,
} from "@/lib/weather/earth-weather-raster";

const MAP = {
  width: 700,
  height: 420,
  tileSize: 256,
};

const MODEL_COLORS = [
  "#0c568f",
  "#cc5c45",
  "#6d55a5",
  "#18806e",
  "#bc7c1d",
  "#b94778",
] as const;

const HONG_KONG_REFERENCE = {
  longitude: 114.1694,
  latitude: 22.3193,
  outerLongitude: 114.65,
} as const;

interface MapView {
  longitude: number;
  latitude: number;
  zoom: number;
}

interface PointerPosition {
  x: number;
  y: number;
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

interface PinchState {
  startDistance: number;
  startZoom: number;
}

interface TrackFeature {
  id: string;
  model: string;
  geometry: {
    type: "Point" | "LineString";
    coordinates: number[] | number[][];
  };
  properties: Record<string, unknown>;
}

type TrackSource = "snapshot" | "active";

interface DisplayTrackFeature extends TrackFeature {
  source: TrackSource;
}

interface ProjectedTrackLine {
  id: string;
  isForecast: boolean;
  model: string;
  path: string;
  source: TrackSource;
}

interface ProjectedTrackPoint {
  forecastDateLabel: string | null;
  forecastDateTime: string | null;
  id: string;
  isForecast: boolean;
  isCurrent: boolean;
  model: string;
  source: TrackSource;
  x: number;
  y: number;
  tooltip: string;
}

interface TrackAreaFeature {
  id: string;
  forecastPeriod: string;
  coordinates: number[][];
}

interface ProjectedTrackArea {
  id: string;
  forecastPeriod: string;
  path: string;
}

interface DecodedModelFrame {
  rainfall: EarthWeatherScalarGrid;
  wind: EarthWeatherVectorGrid | null;
}

interface DecodedModelResult {
  frame: DecodedModelFrame | null;
  key: string;
}

interface WindParticle {
  age: number;
  x: number;
  y: number;
}

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(maximum, Math.max(minimum, value));
}

function project(longitude: number, latitude: number) {
  const safeLatitude = clamp(latitude, -85.051129, 85.051129);
  const latitudeRadians = (safeLatitude * Math.PI) / 180;
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
    latitude: (Math.atan(Math.sinh(mercatorY)) * 180) / Math.PI,
  };
}

function toScreen(view: MapView, longitude: number, latitude: number) {
  const center = project(view.longitude, view.latitude);
  const point = project(longitude, latitude);
  const pixelsPerWorld = MAP.tileSize * 2 ** view.zoom;
  return {
    x: MAP.width / 2 + (point.x - center.x) * pixelsPerWorld,
    y: MAP.height / 2 + (point.y - center.y) * pixelsPerWorld,
  };
}

function fromScreen(view: MapView, x: number, y: number) {
  const center = project(view.longitude, view.latitude);
  const pixelsPerWorld = MAP.tileSize * 2 ** view.zoom;
  return unproject(
    center.x + (x - MAP.width / 2) / pixelsPerWorld,
    center.y + (y - MAP.height / 2) / pixelsPerWorld,
  );
}

const RAINFALL_GRADIENT = [
  [0, [230, 230, 230]],
  [0.5, [165, 247, 247]],
  [2, [1, 255, 255]],
  [5, [2, 214, 206]],
  [10, [0, 189, 23]],
  [20, [73, 214, 33]],
  [30, [165, 231, 0]],
  [40, [255, 222, 0]],
  [50, [255, 173, 0]],
  [70, [255, 99, 0]],
  [100, [206, 49, 0]],
] as const;

const RAINFALL_SCALE_LABELS = [
  { mm: 0, label: "0" },
  { mm: 10, label: "10" },
  { mm: 30, label: "30" },
  { mm: 50, label: "50" },
  { mm: 100, label: "100" },
] as const;

const RAINFALL_GRADIENT_CSS = RAINFALL_GRADIENT.map(
  ([threshold, [r, g, b]]) => `rgb(${r},${g},${b}) ${(threshold / 100) * 100}%`,
).join(", ");

function rainfallColor(value: number) {
  if (!Number.isFinite(value) || value < 0.2) return null;
  const upperIndex = RAINFALL_GRADIENT.findIndex(
    ([threshold]) => threshold >= value,
  );
  if (upperIndex <= 0) {
    const [, color] =
      upperIndex === 0
        ? RAINFALL_GRADIENT[0]
        : RAINFALL_GRADIENT.at(-1)!;
    return `rgba(${color[0]}, ${color[1]}, ${color[2]}, 0.56)`;
  }
  const [lowerValue, lower] = RAINFALL_GRADIENT[upperIndex - 1];
  const [upperValue, upper] = RAINFALL_GRADIENT[upperIndex];
  const fraction = clamp(
    (value - lowerValue) / (upperValue - lowerValue),
    0,
    1,
  );
  const color = lower.map((channel, index) =>
    Math.round(channel + (upper[index] - channel) * fraction),
  );
  return `rgba(${color[0]}, ${color[1]}, ${color[2]}, 0.56)`;
}

function modelTimeLabel(value: string) {
  return new Intl.DateTimeFormat("en-HK", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Hong_Kong",
  }).format(new Date(value));
}

function isCoordinate(value: unknown): value is number[] {
  return (
    Array.isArray(value) &&
    value.length >= 2 &&
    typeof value[0] === "number" &&
    Number.isFinite(value[0]) &&
    typeof value[1] === "number" &&
    Number.isFinite(value[1])
  );
}

function trackFeatures(geoJson: Record<string, unknown>): TrackFeature[] {
  if (!Array.isArray(geoJson.features)) return [];

  return geoJson.features.flatMap((rawFeature, index) => {
    if (
      typeof rawFeature !== "object" ||
      rawFeature === null ||
      !("geometry" in rawFeature)
    ) {
      return [];
    }
    const rawGeometry = rawFeature.geometry;
    if (
      typeof rawGeometry !== "object" ||
      rawGeometry === null ||
      !("type" in rawGeometry) ||
      !("coordinates" in rawGeometry)
    ) {
      return [];
    }

    const type = rawGeometry.type;
    const coordinates = rawGeometry.coordinates;
    if (
      (type !== "Point" && type !== "LineString") ||
      (type === "Point" && !isCoordinate(coordinates)) ||
      (type === "LineString" &&
        (!Array.isArray(coordinates) ||
          !coordinates.every(isCoordinate) ||
          coordinates.length < 2))
    ) {
      return [];
    }

    const rawProperties =
      "properties" in rawFeature &&
      typeof rawFeature.properties === "object" &&
      rawFeature.properties !== null
        ? rawFeature.properties as Record<string, unknown>
        : {};
    const modelCandidate =
      rawProperties.model ??
      rawProperties.modelName ??
      rawProperties.forecastModel;
    const model =
      typeof modelCandidate === "string" && modelCandidate.trim()
        ? modelCandidate.trim()
        : "HKO Official";

    return [{
      id: `track-feature-${index}`,
      model,
      geometry: {
        type,
        coordinates,
      } as TrackFeature["geometry"],
      properties: rawProperties,
    }];
  });
}

function trackAreaFeatures(
  geoJson: Record<string, unknown> | null,
): TrackAreaFeature[] {
  if (!geoJson || !Array.isArray(geoJson.features)) return [];

  return geoJson.features.flatMap((rawFeature, index) => {
    if (
      typeof rawFeature !== "object" ||
      rawFeature === null ||
      !("geometry" in rawFeature)
    ) {
      return [];
    }
    const geometry = rawFeature.geometry;
    if (
      typeof geometry !== "object" ||
      geometry === null ||
      !("type" in geometry) ||
      geometry.type !== "Polygon" ||
      !("coordinates" in geometry) ||
      !Array.isArray(geometry.coordinates) ||
      !Array.isArray(geometry.coordinates[0]) ||
      !geometry.coordinates[0].every(isCoordinate)
    ) {
      return [];
    }
    const properties =
      "properties" in rawFeature &&
      typeof rawFeature.properties === "object" &&
      rawFeature.properties !== null
        ? rawFeature.properties as Record<string, unknown>
        : {};
    const forecastPeriod =
      typeof properties.forecastPeriod === "string"
        ? properties.forecastPeriod
        : "Potential track area";
    return [{
      id: `track-area-${index}`,
      forecastPeriod,
      coordinates: geometry.coordinates[0] as number[][],
    }];
  });
}

function allCoordinates(
  features: readonly TrackFeature[],
  areas: readonly TrackAreaFeature[],
) {
  return [
    ...features.flatMap((feature) =>
    feature.geometry.type === "Point"
      ? [feature.geometry.coordinates as number[]]
      : feature.geometry.coordinates as number[][],
    ),
    ...areas.flatMap((area) => area.coordinates),
  ];
}

function fitTrack(
  features: readonly TrackFeature[],
  areas: readonly TrackAreaFeature[],
) {
  const coordinates = allCoordinates(features, areas);
  if (coordinates.length === 0) {
    return {
      view: { longitude: 114.135, latitude: 22.375, zoom: 5 },
      minZoom: 2,
      maxZoom: 11,
    };
  }

  const projected = coordinates.map(([longitude, latitude]) =>
    project(longitude, latitude),
  );
  const minimumX = Math.min(...projected.map((point) => point.x));
  const maximumX = Math.max(...projected.map((point) => point.x));
  const minimumY = Math.min(...projected.map((point) => point.y));
  const maximumY = Math.max(...projected.map((point) => point.y));
  const center = unproject(
    (minimumX + maximumX) / 2,
    (minimumY + maximumY) / 2,
  );
  const horizontalSpan = Math.max(maximumX - minimumX, 0.00001);
  const verticalSpan = Math.max(maximumY - minimumY, 0.00001);
  const horizontalZoom = Math.log2(
    (MAP.width - 110) / (MAP.tileSize * horizontalSpan),
  );
  const verticalZoom = Math.log2(
    (MAP.height - 90) / (MAP.tileSize * verticalSpan),
  );
  const zoom = clamp(Math.min(horizontalZoom, verticalZoom), 2, 10.5);

  return {
    view: { ...center, zoom },
    minZoom: Math.max(2, zoom - 1),
    maxZoom: Math.min(14, zoom + 6),
  };
}

function plainText(value: string) {
  return value
    .replace(/<br\s*\/?>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/\s+/g, " ")
    .trim();
}

function descriptionField(description: string, label: string) {
  const escapedLabel = label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const tableCell = description.match(
    new RegExp(
      `${escapedLabel}<\\/th>\\s*<td[^>]*>([\\s\\S]*?)<\\/td>`,
      "i",
    ),
  );
  if (tableCell?.[1]) return plainText(tableCell[1]);
  const plain = plainText(description);
  const inline = plain.match(
    new RegExp(`${escapedLabel}\\s*:?\\s*([^|;]+)`, "i"),
  );
  return inline?.[1]?.trim() ?? null;
}

function pointTooltip(properties: Record<string, unknown>) {
  const description =
    typeof properties.description === "string" ? properties.description : "";
  const dateTime = pointDateTime(properties);
  const classification =
    typeof properties.classification === "string"
      ? properties.classification
      : descriptionField(description, "Classification");
  const wind =
    typeof properties.maximumWind === "string"
      ? properties.maximumWind
      : descriptionField(description, "Maximum sustained wind near centre");
  return [dateTime, classification, wind].filter(Boolean).join(" · ");
}

function pointDateTime(properties: Record<string, unknown>) {
  const description =
    typeof properties.description === "string" ? properties.description : "";
  return typeof properties.dateTime === "string"
    ? properties.dateTime
    : descriptionField(description, "Date and time");
}

function trackPointTime(
  properties: Record<string, unknown>,
  referenceTime: number,
) {
  const value = pointDateTime(properties);
  if (!value) return null;

  const fullHkoFormat = value.match(
    /(\d{1,2}):(\d{2})\s*HKT\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})/i,
  );
  const months = [
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
  ];
  if (fullHkoFormat) {
    const month = months.indexOf(fullHkoFormat[4].toLowerCase());
    if (month < 0) return null;
    return Date.UTC(
      Number(fullHkoFormat[5]),
      month,
      Number(fullHkoFormat[3]),
      Number(fullHkoFormat[1]) - 8,
      Number(fullHkoFormat[2]),
    );
  }

  const compactHkoFormat = value.match(
    /(\d{1,2})\s+([A-Za-z]+),?\s+(\d{1,2})(?::(\d{2}))?\s*HKT/i,
  );
  if (compactHkoFormat && Number.isFinite(referenceTime)) {
    const abbreviatedMonth = compactHkoFormat[2].toLowerCase();
    const month = months.findIndex((candidate) =>
      candidate.startsWith(abbreviatedMonth),
    );
    if (month < 0) return null;

    const reference = new Date(referenceTime + 8 * 60 * 60 * 1000);
    const candidate = Date.UTC(
      reference.getUTCFullYear(),
      month,
      Number(compactHkoFormat[1]),
      Number(compactHkoFormat[3]) - 8,
      Number(compactHkoFormat[4] ?? 0),
    );
    const halfYear = 183 * 24 * 60 * 60 * 1000;
    if (candidate - referenceTime > halfYear) {
      const previousYear = new Date(candidate);
      previousYear.setUTCFullYear(previousYear.getUTCFullYear() - 1);
      return previousYear.getTime();
    }
    if (referenceTime - candidate > halfYear) {
      const nextYear = new Date(candidate);
      nextYear.setUTCFullYear(nextYear.getUTCFullYear() + 1);
      return nextYear.getTime();
    }
    return candidate;
  }

  const normalized = value.replace(/\bHKT\b/i, " GMT+0800");
  const direct = Date.parse(normalized);
  return Number.isFinite(direct) ? direct : null;
}

function modelColor(model: string, models: readonly string[]) {
  const index = Math.max(0, models.indexOf(model));
  return MODEL_COLORS[index % MODEL_COLORS.length];
}

function forecastDateLabel(
  properties: Record<string, unknown>,
  referenceTime: number,
) {
  const pointTime = trackPointTime(properties, referenceTime);
  if (pointTime === null) return null;
  return new Intl.DateTimeFormat("en-HK", {
    day: "numeric",
    month: "short",
    timeZone: "Asia/Hong_Kong",
  }).format(new Date(pointTime));
}

export function TyphoonTrackMap({
  activeAsOf,
  activeGeoJson,
  asOf,
  geoJson,
  isFuture = false,
  modelFrame,
  modelStatus,
  potentialTrackAreaGeoJson,
}: {
  activeAsOf: string;
  activeGeoJson: Record<string, unknown>;
  asOf: string;
  geoJson: Record<string, unknown>;
  isFuture?: boolean;
  modelFrame: TyphoonModelFrame | null;
  modelStatus: "idle" | "loading" | "ready" | "unavailable";
  potentialTrackAreaGeoJson: Record<string, unknown> | null;
}) {
  const snapshotFeatures = useMemo(() => trackFeatures(geoJson), [geoJson]);
  const activeFeatures = useMemo(
    () => trackFeatures(activeGeoJson),
    [activeGeoJson],
  );
  const features = useMemo<DisplayTrackFeature[]>(() => {
    const activeIsSelected =
      JSON.stringify(activeGeoJson) === JSON.stringify(geoJson);
    const sourcedActive = activeFeatures.map((feature) => ({
      ...feature,
      id: `active-${feature.id}`,
      source: "active" as const,
    }));
    if (activeIsSelected) return sourcedActive;
    return [
      ...snapshotFeatures.map((feature) => ({
        ...feature,
        id: `snapshot-${feature.id}`,
        source: "snapshot" as const,
      })),
      ...sourcedActive,
    ];
  }, [activeFeatures, activeGeoJson, geoJson, snapshotFeatures]);
  const areas = useMemo(
    () => trackAreaFeatures(potentialTrackAreaGeoJson),
    [potentialTrackAreaGeoJson],
  );
  const fitted = useMemo(() => fitTrack(features, areas), [areas, features]);
  const [view, setView] = useState<MapView>(fitted.view);
  const [dragging, setDragging] = useState(false);
  const [activeTooltipPointId, setActiveTooltipPointId] = useState<
    string | null
  >(null);
  const [decodedModelResult, setDecodedModelResult] =
    useState<DecodedModelResult | null>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const rainfallCanvasRef = useRef<HTMLCanvasElement>(null);
  const windCanvasRef = useRef<HTMLCanvasElement>(null);
  const dragState = useRef<DragState | null>(null);
  const pinchState = useRef<PinchState | null>(null);
  const pointers = useRef(new Map<number, PointerPosition>());

  const models = useMemo(
    () => Array.from(new Set(features.map((feature) => feature.model))),
    [features],
  );

  useEffect(() => {
    if (!modelFrame) return;
    const controller = new AbortController();
    const frameKey = [
      modelFrame.validAt,
      modelFrame.rainfall.imageUrl,
      modelFrame.wind?.imageUrl ?? "",
    ].join("|");
    void Promise.all([
      decodeEarthWeatherRainfall(
        modelFrame.rainfall.imageUrl,
        controller.signal,
      ),
      modelFrame.wind
        ? decodeEarthWeatherWind(modelFrame.wind.imageUrl, controller.signal)
        : Promise.resolve(null),
    ])
      .then(([rainfall, wind]) => {
        if (controller.signal.aborted) return;
        const boundsMatch =
          wind === null ||
          (
            Math.abs(rainfall.header.north - wind.header.north) < 0.001 &&
            Math.abs(rainfall.header.south - wind.header.south) < 0.001 &&
            Math.abs(rainfall.header.east - wind.header.east) < 0.001 &&
            Math.abs(rainfall.header.west - wind.header.west) < 0.001
          );
        if (!boundsMatch) {
          throw new Error("ECMWF rainfall and wind domains do not match");
        }
        setDecodedModelResult({
          frame: { rainfall, wind },
          key: frameKey,
        });
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setDecodedModelResult({ frame: null, key: frameKey });
        }
      });
    return () => controller.abort();
  }, [modelFrame, modelStatus]);

  const modelFrameKey = modelFrame
    ? [
        modelFrame.validAt,
        modelFrame.rainfall.imageUrl,
        modelFrame.wind?.imageUrl ?? "",
      ].join("|")
    : null;
  const currentDecodedModel =
    modelFrameKey && decodedModelResult?.key === modelFrameKey
      ? decodedModelResult
      : null;
  const decodedModelFrame = currentDecodedModel?.frame ?? null;
  const decodeStatus: "idle" | "loading" | "ready" | "unavailable" =
    !modelFrame
      ? modelStatus
      : !currentDecodedModel
        ? "loading"
        : currentDecodedModel.frame
          ? "ready"
          : "unavailable";

  useEffect(() => {
    const canvas = rainfallCanvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;
    context.clearRect(0, 0, MAP.width, MAP.height);
    const grid = decodedModelFrame?.rainfall;
    if (!grid) return;

    const { header, values } = grid;
    const columns = Array.from({ length: header.width + 1 }, (_, column) =>
      toScreen(
        view,
        header.west + (column - 0.5) * header.longitudeStep,
        view.latitude,
      ).x,
    );
    const rows = Array.from({ length: header.height + 1 }, (_, row) =>
      toScreen(
        view,
        view.longitude,
        header.north - (row - 0.5) * header.latitudeStep,
      ).y,
    );
    const colors = new Map<number, string | null>();
    for (let row = 0; row < header.height; row += 1) {
      const top = Math.min(rows[row], rows[row + 1]);
      const bottom = Math.max(rows[row], rows[row + 1]);
      if (bottom < 0 || top > MAP.height) continue;
      for (let column = 0; column < header.width; column += 1) {
        const left = Math.min(columns[column], columns[column + 1]);
        const right = Math.max(columns[column], columns[column + 1]);
        if (right < 0 || left > MAP.width) continue;
        const value = values[row * header.width + column];
        const colorKey = Math.round(value * 2);
        let color = colors.get(colorKey);
        if (color === undefined) {
          color = rainfallColor(colorKey / 2);
          colors.set(colorKey, color);
        }
        if (!color) continue;
        context.fillStyle = color;
        context.fillRect(
          Math.floor(left),
          Math.floor(top),
          Math.max(1, Math.ceil(right - left) + 1),
          Math.max(1, Math.ceil(bottom - top) + 1),
        );
      }
    }
  }, [decodedModelFrame, view]);

  useEffect(() => {
    const canvas = windCanvasRef.current;
    const context = canvas?.getContext("2d");
    const grid = decodedModelFrame?.wind;
    if (!canvas || !context) return;
    context.clearRect(0, 0, MAP.width, MAP.height);
    if (!grid) return;

    const reducedMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    const drawStaticVectors = () => {
      context.strokeStyle = "rgba(255, 255, 255, 0.82)";
      context.lineWidth = 1.15;
      context.shadowColor = "rgba(12, 34, 48, 0.38)";
      context.shadowBlur = 2;
      for (let y = 18; y < MAP.height; y += 28) {
        for (let x = 18; x < MAP.width; x += 28) {
          const location = fromScreen(view, x, y);
          const vector = sampleEarthWeatherVector(
            grid,
            location.longitude,
            location.latitude,
          );
          if (!vector) continue;
          const speed = Math.hypot(vector[0], vector[1]);
          if (speed < 0.2) continue;
          const length = clamp(speed * 0.38, 2.5, 9);
          context.beginPath();
          context.moveTo(x, y);
          context.lineTo(
            x + vector[0] / speed * length,
            y - vector[1] / speed * length,
          );
          context.stroke();
        }
      }
      context.shadowBlur = 0;
    };
    if (reducedMotion) {
      drawStaticVectors();
      return;
    }

    const particles: WindParticle[] = [];
    const maximumAge = 65;
    const resetParticle = (particle: WindParticle) => {
      for (let attempt = 0; attempt < 12; attempt += 1) {
        particle.x = Math.random() * MAP.width;
        particle.y = Math.random() * MAP.height;
        const location = fromScreen(view, particle.x, particle.y);
        if (
          sampleEarthWeatherVector(
            grid,
            location.longitude,
            location.latitude,
          )
        ) {
          particle.age = Math.floor(Math.random() * maximumAge);
          return;
        }
      }
      particle.age = maximumAge;
    };
    for (let index = 0; index < 210; index += 1) {
      const particle = { age: maximumAge, x: 0, y: 0 };
      resetParticle(particle);
      particles.push(particle);
    }

    let animationFrame = 0;
    let previousTimestamp = 0;
    const animate = (timestamp: number) => {
      animationFrame = requestAnimationFrame(animate);
      if (timestamp - previousTimestamp < 32) return;
      previousTimestamp = timestamp;
      context.globalCompositeOperation = "destination-out";
      context.fillStyle = "rgba(0, 0, 0, 0.12)";
      context.fillRect(0, 0, MAP.width, MAP.height);
      context.globalCompositeOperation = "source-over";
      context.strokeStyle = "rgba(255, 255, 255, 0.78)";
      context.lineWidth = 1.15;
      context.shadowColor = "rgba(12, 34, 48, 0.42)";
      context.shadowBlur = 1.5;
      const secondsPerFrame = 1_800 / 2 ** Math.max(0, view.zoom - 5);

      particles.forEach((particle) => {
        if (particle.age >= maximumAge) {
          resetParticle(particle);
          return;
        }
        const location = fromScreen(view, particle.x, particle.y);
        const vector = sampleEarthWeatherVector(
          grid,
          location.longitude,
          location.latitude,
        );
        if (!vector) {
          particle.age = maximumAge;
          return;
        }
        const cosine = Math.max(
          0.15,
          Math.cos(location.latitude * Math.PI / 180),
        );
        const destination = toScreen(
          view,
          location.longitude +
            vector[0] * secondsPerFrame / (111_320 * cosine),
          location.latitude + vector[1] * secondsPerFrame / 111_320,
        );
        if (
          destination.x < 0 ||
          destination.x > MAP.width ||
          destination.y < 0 ||
          destination.y > MAP.height
        ) {
          particle.age = maximumAge;
          return;
        }
        context.beginPath();
        context.moveTo(particle.x, particle.y);
        context.lineTo(destination.x, destination.y);
        context.stroke();
        particle.x = destination.x;
        particle.y = destination.y;
        particle.age += 1;
      });
      context.shadowBlur = 0;
    };
    animationFrame = requestAnimationFrame(animate);
    return () => {
      cancelAnimationFrame(animationFrame);
      context.clearRect(0, 0, MAP.width, MAP.height);
    };
  }, [decodedModelFrame, view]);

  const mapGeometry = useMemo(() => {
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
    const tiles = [];
    const tileCount = 2 ** tileZoom;

    for (let tileY = firstRow; tileY <= lastRow; tileY += 1) {
      if (tileY < 0 || tileY >= tileCount) continue;
      for (let tileX = firstColumn; tileX <= lastColumn; tileX += 1) {
        const wrappedX = ((tileX % tileCount) + tileCount) % tileCount;
        tiles.push({
          x: wrappedX,
          y: tileY,
          screenX: (tileX * MAP.tileSize - viewportLeft) * renderScale,
          screenY: (tileY * MAP.tileSize - viewportTop) * renderScale,
        });
      }
    }
    return { renderScale, tileZoom, tiles };
  }, [view]);

  const projectedFeatures = useMemo(() => {
    const center = project(view.longitude, view.latitude);
    const pixelsPerWorld = MAP.tileSize * 2 ** view.zoom;
    const toScreen = ([longitude, latitude]: number[]) => {
      const point = project(longitude, latitude);
      return {
        x: MAP.width / 2 + (point.x - center.x) * pixelsPerWorld,
        y: MAP.height / 2 + (point.y - center.y) * pixelsPerWorld,
      };
    };
    const hongKongCenter = toScreen([
      HONG_KONG_REFERENCE.longitude,
      HONG_KONG_REFERENCE.latitude,
    ]);
    const hongKongOuterEdge = toScreen([
      HONG_KONG_REFERENCE.outerLongitude,
      HONG_KONG_REFERENCE.latitude,
    ]);
    const hongKongReference = {
      ...hongKongCenter,
      radius: Math.max(
        5,
        Math.abs(hongKongOuterEdge.x - hongKongCenter.x),
      ),
    };
    const lines: ProjectedTrackLine[] = [];
    const points: ProjectedTrackPoint[] = [];
    const pointFeatures = features.filter(
      (feature) => feature.geometry.type === "Point",
    );
    const asOfTime = Date.parse(asOf);
    const activeAsOfTime = Date.parse(activeAsOf);
    const currentPointFor = (
      source: TrackSource,
      referenceTime: number,
    ) => {
      const sourcePoints = pointFeatures.filter(
        (feature) => feature.source === source,
      );
      const nonForecastPoints = sourcePoints.filter(
        (feature) =>
          !/\bforecast/i.test(JSON.stringify(feature.properties)),
      );
      return (
        nonForecastPoints
          .map((feature) => ({
            feature,
            time: trackPointTime(feature.properties, referenceTime),
          }))
          .filter(
            (candidate): candidate is {
              feature: DisplayTrackFeature;
              time: number;
            } =>
              candidate.time !== null &&
              (!Number.isFinite(referenceTime) ||
                candidate.time <= referenceTime + 3 * 60 * 60 * 1000),
          )
          .sort((first, second) => second.time - first.time)[0]?.feature ??
        nonForecastPoints.at(-1) ??
        sourcePoints.at(-1)
      );
    };
    const currentPoints = {
      active: currentPointFor("active", activeAsOfTime),
      snapshot: currentPointFor("snapshot", asOfTime),
    };
    const projectedAreas: ProjectedTrackArea[] = areas.map((area) => ({
      id: area.id,
      forecastPeriod: area.forecastPeriod,
      path: `${area.coordinates
        .map((coordinate, index) => {
          const point = toScreen(coordinate);
          return `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`;
        })
        .join(" ")} Z`,
    }));

    features.forEach((feature) => {
      if (feature.geometry.type === "LineString") {
        const coordinates = feature.geometry.coordinates as number[][];
        const path = coordinates
          .map((coordinate, index) => {
            const point = toScreen(coordinate);
            return `${index === 0 ? "M" : "L"} ${point.x} ${point.y}`;
          })
          .join(" ");
        lines.push({
          id: feature.id,
          isForecast: /\bforecast/i.test(
            JSON.stringify(feature.properties),
          ),
          model: feature.model,
          path,
          source: feature.source,
        });
        return;
      }

      const referenceTime =
        feature.source === "active" ? activeAsOfTime : asOfTime;
      const sourceCurrentPoint = currentPoints[feature.source];
      const currentPointTime = sourceCurrentPoint
        ? trackPointTime(sourceCurrentPoint.properties, referenceTime)
        : null;
      const pointDate = pointDateTime(feature.properties);
      const pointTime = trackPointTime(feature.properties, referenceTime);
      const explicitlyForecast = /\bforecast/i.test(
        JSON.stringify(feature.properties),
      );
      const isForecast =
        feature !== sourceCurrentPoint &&
        (explicitlyForecast ||
          (pointTime !== null &&
            currentPointTime !== null &&
            pointTime > currentPointTime));
      const details = pointTooltip(feature.properties);
      const tooltip =
        isForecast && pointDate
          ? `Forecast position · ${pointDate}${details && details !== pointDate ? ` · ${details.replace(`${pointDate} · `, "")}` : ""}`
          : details;
      if (!tooltip) return;
      const point = toScreen(feature.geometry.coordinates as number[]);
      points.push({
        forecastDateLabel: isForecast
          ? forecastDateLabel(feature.properties, referenceTime)
          : null,
        forecastDateTime: isForecast ? pointDate : null,
        id: feature.id,
        isForecast,
        isCurrent:
          feature === (currentPoints.snapshot ?? currentPoints.active),
        model: feature.model,
        source: feature.source,
        x: point.x,
        y: point.y,
        tooltip,
      });
    });
    return {
      areas: projectedAreas,
      hasSnapshot: features.some((feature) => feature.source === "snapshot") || isFuture,
      hongKongReference,
      lines,
      points,
    };
  }, [activeAsOf, areas, asOf, features, isFuture, view]);
  const activeForecastPoint =
    projectedFeatures.points.find(
      (point) =>
        point.id === activeTooltipPointId &&
        point.isForecast &&
        point.forecastDateTime,
    ) ?? null;

  function clampZoom(zoom: number) {
    return clamp(zoom, fitted.minZoom, fitted.maxZoom);
  }

  function zoomBy(amount: number) {
    setView((current) => ({
      ...current,
      zoom: clampZoom(current.zoom + amount),
    }));
  }

  function panByPixels(deltaX: number, deltaY: number) {
    setView((current) => {
      const center = project(current.longitude, current.latitude);
      const pixelsPerWorld = MAP.tileSize * 2 ** current.zoom;
      return {
        ...unproject(
          center.x + deltaX / pixelsPerWorld,
          center.y + deltaY / pixelsPerWorld,
        ),
        zoom: current.zoom,
      };
    });
  }

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return;
    const handleWheel = (event: globalThis.WheelEvent) => {
      event.preventDefault();
      event.stopPropagation();
      if (event.deltaY === 0) return;
      setView((current) => ({
        ...current,
        zoom: clamp(
          current.zoom + (event.deltaY < 0 ? 0.25 : -0.25),
          fitted.minZoom,
          fitted.maxZoom,
        ),
      }));
    };
    viewport.addEventListener("wheel", handleWheel, { passive: false });
    return () => viewport.removeEventListener("wheel", handleWheel);
  }, [fitted.maxZoom, fitted.minZoom]);

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
      setView((current) => ({
        ...current,
        zoom: clampZoom(
          pinch.startZoom + Math.log2(distance / pinch.startDistance),
        ),
      }));
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
    setView({ ...geographic, zoom: drag.zoom });
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
    <div className="typhoon-track-map">
      <div className="weather-overview-map-viewport" ref={viewportRef}>
        <svg
          className="weather-overview-map-chart typhoon-track-map-chart"
          data-dragging={dragging ? "true" : undefined}
          viewBox={`0 0 ${MAP.width} ${MAP.height}`}
          role="application"
          tabIndex={0}
          aria-label="Interactive map of the selected tropical cyclone forecast track and 70 percent Potential Track Area. Drag or use arrow keys to pan; scroll or use plus and minus to zoom."
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={endPointerInteraction}
          onPointerCancel={endPointerInteraction}
          onKeyDown={handleKeyDown}
        >
          <rect className="temperature-map-water" width={MAP.width} height={MAP.height} />
          <g aria-hidden="true">
            {mapGeometry.tiles.map((tile) => (
              <image
                className="typhoon-map-tile"
                href={`https://a.basemaps.cartocdn.com/light_nolabels/${mapGeometry.tileZoom}/${tile.x}/${tile.y}@2x.png`}
                x={tile.screenX}
                y={tile.screenY}
                width={MAP.tileSize * mapGeometry.renderScale}
                height={MAP.tileSize * mapGeometry.renderScale}
                key={`${mapGeometry.tileZoom}-${tile.x}-${tile.y}-${tile.screenX}`}
              />
            ))}
          </g>
          <rect
            className="temperature-map-desaturating-layer"
            width={MAP.width}
            height={MAP.height}
            aria-hidden="true"
          />
          <foreignObject
            className="typhoon-model-rainfall-layer"
            x="0"
            y="0"
            width={MAP.width}
            height={MAP.height}
            aria-hidden="true"
          >
            <canvas
              ref={rainfallCanvasRef}
              width={MAP.width}
              height={MAP.height}
            />
          </foreignObject>
          <g className="typhoon-track-areas" aria-hidden="true">
            {projectedFeatures.areas.map((area) => (
              <path
                className={
                  area.forecastPeriod === "72-120 hours"
                    ? "typhoon-track-area-later"
                    : "typhoon-track-area-earlier"
                }
                d={area.path}
                key={area.id}
              />
            ))}
          </g>
          <foreignObject
            className="typhoon-model-wind-layer"
            x="0"
            y="0"
            width={MAP.width}
            height={MAP.height}
            aria-hidden="true"
          >
            <canvas ref={windCanvasRef} width={MAP.width} height={MAP.height} />
          </foreignObject>
          <g
            className="typhoon-track-lines"
            data-has-snapshot={
              projectedFeatures.hasSnapshot ? "true" : undefined
            }
            aria-hidden="true"
          >
            {projectedFeatures.lines.map((line) => (
              <path
                className="typhoon-track-line"
                data-forecast={line.isForecast ? "true" : undefined}
                data-source={line.source}
                d={line.path}
                stroke={modelColor(line.model, models)}
                key={line.id}
              />
            ))}
          </g>
          <g
            className="typhoon-track-points"
            data-has-snapshot={
              projectedFeatures.hasSnapshot ? "true" : undefined
            }
          >
            {projectedFeatures.points.map((point) =>
              point.isCurrent ? (
                <g
                  transform={`translate(${point.x} ${point.y})`}
                  aria-label={`Current tropical cyclone position · ${point.tooltip}`}
                  key={point.id}
                >
                  <g className="typhoon-current-symbol">
                    <image
                      href="/typhoon-current-position.svg"
                      x="-14"
                      y="-14"
                      width="28"
                      height="28"
                    />
                  </g>
                  <title>{point.tooltip}</title>
                </g>
              ) : (
                <circle
                  data-forecast={point.isForecast ? "true" : undefined}
                  data-source={point.source}
                  cx={point.x}
                  cy={point.y}
                  r="4.4"
                  fill={modelColor(point.model, models)}
                  aria-label={
                    point.forecastDateTime
                      ? `Predicted tropical cyclone position for ${point.forecastDateTime}`
                      : point.tooltip
                  }
                  tabIndex={point.isForecast ? 0 : undefined}
                  key={point.id}
                  onPointerEnter={() => {
                    if (point.isForecast) setActiveTooltipPointId(point.id);
                  }}
                  onPointerLeave={() =>
                    setActiveTooltipPointId((activeId) =>
                      activeId === point.id ? null : activeId,
                    )
                  }
                  onFocus={() => {
                    if (point.isForecast) setActiveTooltipPointId(point.id);
                  }}
                  onBlur={() =>
                    setActiveTooltipPointId((activeId) =>
                      activeId === point.id ? null : activeId,
                    )
                  }
                >
                  {point.isForecast ? null : <title>{point.tooltip}</title>}
                </circle>
              ),
            )}
          </g>
          <g className="typhoon-track-date-labels" aria-hidden="true">
            {projectedFeatures.points.map((point) =>
              (point.source === "snapshot" ||
                !projectedFeatures.hasSnapshot) &&
              point.isForecast &&
              point.forecastDateLabel ? (
                <g
                  data-source={point.source}
                  transform={`translate(${point.x} ${point.y - 13})`}
                  key={`date-${point.id}`}
                >
                  <rect x="-20" y="-8" width="40" height="15" rx="7.5" />
                  <text x="0" y="0" dy="0.3em" textAnchor="middle">
                    {point.forecastDateLabel}
                  </text>
                </g>
              ) : null,
            )}
          </g>
          <g className="typhoon-hong-kong-reference">
            <circle
              className="typhoon-hong-kong-reference-ring"
              cx={projectedFeatures.hongKongReference.x}
              cy={projectedFeatures.hongKongReference.y}
              r={projectedFeatures.hongKongReference.radius}
              aria-hidden="true"
            />
            <circle
              className="typhoon-hong-kong-reference-point"
              cx={projectedFeatures.hongKongReference.x}
              cy={projectedFeatures.hongKongReference.y}
              r="4.2"
              aria-label="Hong Kong"
            >
              <title>Hong Kong</title>
            </circle>
          </g>
        </svg>

        {activeForecastPoint ? (
          <div
            className="typhoon-forecast-tooltip"
            role="tooltip"
            style={{
              left: `${(activeForecastPoint.x / MAP.width) * 100}%`,
              top: `${(activeForecastPoint.y / MAP.height) * 100}%`,
            }}
          >
            {activeForecastPoint.tooltip}
          </div>
        ) : null}

        <div className="temperature-map-controls" aria-label="Map zoom controls">
          <button
            type="button"
            aria-label="Zoom in"
            disabled={view.zoom >= fitted.maxZoom}
            onClick={() => zoomBy(0.25)}
          >
            +
          </button>
          <button
            type="button"
            aria-label="Zoom out"
            disabled={view.zoom <= fitted.minZoom}
            onClick={() => zoomBy(-0.25)}
          >
            −
          </button>
          <button
            type="button"
            aria-label="Reset map view"
            title="Reset view"
            onClick={() => setView(fitted.view)}
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

        <div className="typhoon-track-legend" aria-label="Track versions">
          {decodeStatus === "ready" && modelFrame ? (
            <>
              <span title={`${modelTimeLabel(modelFrame.validAt)} HKT`}>
                <i className="typhoon-model-rainfall-key" />
                ECMWF Rain
              </span>
              {decodedModelFrame?.wind ? (
                <span title={`${modelTimeLabel(modelFrame.validAt)} HKT`}>
                  <i className="typhoon-model-wind-key" />
                  ECMWF Wind
                </span>
              ) : null}
              <span className="typhoon-model-time">
                {modelTimeLabel(modelFrame.validAt)}
              </span>
            </>
          ) : decodeStatus === "loading" || modelStatus === "loading" ? (
            <span className="typhoon-model-status">Loading ECMWF layers…</span>
          ) : decodeStatus === "unavailable" ||
            modelStatus === "unavailable" ? (
            <span className="typhoon-model-status">
              No matching ECMWF frame
            </span>
          ) : null}
          {projectedFeatures.hasSnapshot ? (
            isFuture ? (
              <span>
                <i className="typhoon-track-future-key" />
                Future prediction
              </span>
            ) : (
              <span>
                <i className="typhoon-track-snapshot-key" />
                Snapshot
              </span>
            )
          ) : null}
          <span>
            <i className="typhoon-track-newest-key" />
            Newest prediction
          </span>
          {areas.length > 0 ? (
            <>
              <span>
                <i className="typhoon-track-area-key typhoon-track-area-key-earlier" />
                70% area · 0–72h
              </span>
              {areas.some(
                (area) => area.forecastPeriod === "72-120 hours",
              ) ? (
                <span>
                  <i className="typhoon-track-area-key typhoon-track-area-key-later" />
                  70% area · 72–120h
                </span>
              ) : null}
            </>
          ) : null}
        </div>

        <div className="typhoon-rainfall-scale" role="img" aria-label="Rainfall scale in millimetres per hour">
          <span className="typhoon-rainfall-scale-bar" style={{ background: `linear-gradient(to right, ${RAINFALL_GRADIENT_CSS})` }} />
          <span className="typhoon-rainfall-scale-labels">
            {RAINFALL_SCALE_LABELS.map(({ mm, label }) => (
              <span key={mm} className="typhoon-rainfall-scale-label">
                {label}
              </span>
            ))}
            <span className="typhoon-rainfall-scale-unit">mm/h</span>
          </span>
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
    </div>
  );
}
