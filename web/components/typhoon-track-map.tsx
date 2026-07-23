"use client";

import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
} from "react";

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

interface ProjectedTrackLine {
  id: string;
  model: string;
  path: string;
}

interface ProjectedTrackPoint {
  id: string;
  model: string;
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
  const dateTime =
    typeof properties.dateTime === "string"
      ? properties.dateTime
      : descriptionField(description, "Date and time");
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

function modelColor(model: string, models: readonly string[]) {
  const index = Math.max(0, models.indexOf(model));
  return MODEL_COLORS[index % MODEL_COLORS.length];
}

export function TyphoonTrackMap({
  geoJson,
  potentialTrackAreaGeoJson,
}: {
  geoJson: Record<string, unknown>;
  potentialTrackAreaGeoJson: Record<string, unknown> | null;
}) {
  const features = useMemo(() => trackFeatures(geoJson), [geoJson]);
  const areas = useMemo(
    () => trackAreaFeatures(potentialTrackAreaGeoJson),
    [potentialTrackAreaGeoJson],
  );
  const fitted = useMemo(() => fitTrack(features, areas), [areas, features]);
  const [view, setView] = useState<MapView>(fitted.view);
  const [dragging, setDragging] = useState(false);
  const viewportRef = useRef<HTMLDivElement>(null);
  const dragState = useRef<DragState | null>(null);
  const pinchState = useRef<PinchState | null>(null);
  const pointers = useRef(new Map<number, PointerPosition>());

  const models = useMemo(
    () => Array.from(new Set(features.map((feature) => feature.model))),
    [features],
  );

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
    const lines: ProjectedTrackLine[] = [];
    const points: ProjectedTrackPoint[] = [];
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
          model: feature.model,
          path,
        });
        return;
      }

      const tooltip = pointTooltip(feature.properties);
      if (!tooltip) return;
      const point = toScreen(feature.geometry.coordinates as number[]);
      points.push({
        id: feature.id,
        model: feature.model,
        x: point.x,
        y: point.y,
        tooltip,
      });
    });
    return { areas: projectedAreas, lines, points };
  }, [areas, features, view]);

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
                className="temperature-map-tile"
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
          <g className="typhoon-track-lines" aria-hidden="true">
            {projectedFeatures.lines.map((line) => (
              <path
                d={line.path}
                stroke={modelColor(line.model, models)}
                key={line.id}
              />
            ))}
          </g>
          <g className="typhoon-track-points">
            {projectedFeatures.points.map((point) => (
              <circle
                cx={point.x}
                cy={point.y}
                r="4.4"
                fill={modelColor(point.model, models)}
                aria-label={point.tooltip}
                key={point.id}
              >
                <title>{point.tooltip}</title>
              </circle>
            ))}
          </g>
        </svg>

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

        <div className="typhoon-track-legend" aria-label="Track models">
          {models.map((model) => (
            <span key={model}>
              <i style={{ backgroundColor: modelColor(model, models) }} />
              {model}
            </span>
          ))}
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
