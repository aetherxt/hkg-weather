export const HONG_KONG_LAT = 22.3;
export const HONG_KONG_LNG = 114.2;

export const CHART_CX = 240;
export const CHART_CY = 205;
export const CHART_RH = 155;

// Cap displayed altitude so high-elevation paths
// (sun near zenith in summer HK) remain visible.
const CHART_MAX_ALT = 70;

export function toXY(azimuth: number, altitude: number) {
  const angle = (azimuth * Math.PI) / 180;
  const clampedAlt = Math.max(0, Math.min(CHART_MAX_ALT, altitude));
  const r = CHART_RH * (1 - clampedAlt / CHART_MAX_ALT);
  return {
    x: CHART_CX + r * Math.sin(angle),
    y: CHART_CY - r * Math.cos(angle),
  };
}

// SunCalc v2 returns altitude and azimuth already in degrees;
// no radian conversion needed here.

export interface SkyPoint {
  azimuth: number;
  altitude: number;
  minutes: number;
}

export function sampleSkyPositions(
  date: Date,
  getPos: (d: Date) => { azimuth: number; altitude: number },
  stepMinutes = 10,
): SkyPoint[] {
  const positions: SkyPoint[] = [];
  for (let m = 0; m < 1440; m += stepMinutes) {
    const hkDate = hkDateAtMinutes(date, m);
    const pos = getPos(hkDate);
    positions.push({
      azimuth: chartAzimuth(pos.azimuth),
      altitude: pos.altitude,
      minutes: m,
    });
  }
  return positions;
}

export function visibleArcPath(positions: SkyPoint[]): string | null {
  const segments = visibleArcSegments(positions);

  const paths = segments
    .filter((current) => current.length >= 2)
    .map((current) => {
      const points = current.map((point) => {
        return `${point.x.toFixed(1)},${point.y.toFixed(1)}`;
      });
      return `M ${points.join(" L ")}`;
    });

  return paths.length > 0 ? paths.join(" ") : null;
}

export function visibleArcSegments(
  positions: SkyPoint[],
): { x: number; y: number }[][] {
  const segments: SkyPoint[][] = [];
  let segment: SkyPoint[] = [];

  for (const point of positions) {
    if (point.altitude >= 0) {
      segment.push(point);
    } else if (segment.length > 0) {
      segments.push(segment);
      segment = [];
    }
  }
  if (segment.length > 0) segments.push(segment);

  return segments
    .filter((current) => current.length >= 2)
    .map((current) => current.map((point) => toXY(point.azimuth, point.altitude)));
}

export interface HorizonCrossing {
  azimuth: number;
  minutes: number;
  direction: "rise" | "set";
}

export function findHorizonCrossings(
  positions: SkyPoint[],
): HorizonCrossing[] {
  const crossings: HorizonCrossing[] = [];
  for (let i = 1; i < positions.length; i++) {
    const prev = positions[i - 1];
    const curr = positions[i];
    if (prev.altitude < 0 && curr.altitude >= 0) {
      const f = (0 - prev.altitude) / (curr.altitude - prev.altitude);
      const azimuth = prev.azimuth + f * deltaAzimuth(prev.azimuth, curr.azimuth);
      crossings.push({
        azimuth: normalizeAzimuth(azimuth),
        minutes: Math.round(prev.minutes + f * (curr.minutes - prev.minutes)),
        direction: "rise",
      });
    } else if (prev.altitude >= 0 && curr.altitude < 0) {
      const f = (prev.altitude - 0) / (prev.altitude - curr.altitude);
      const azimuth = curr.azimuth + f * deltaAzimuth(curr.azimuth, prev.azimuth);
      crossings.push({
        azimuth: normalizeAzimuth(azimuth),
        minutes: Math.round(curr.minutes + f * (prev.minutes - curr.minutes)),
        direction: "set",
      });
    }
  }
  return crossings;
}

export function formatMinutes(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

function hkDateAtMinutes(base: Date, minutes: number): Date {
  const dateStr = base.toISOString().slice(0, 10);
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  const hkStr = `${dateStr}T${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:00+08:00`;
  return new Date(hkStr);
}

function deltaAzimuth(from: number, to: number): number {
  let d = to - from;
  if (d > 180) d -= 360;
  if (d < -180) d += 360;
  return d;
}

function normalizeAzimuth(a: number): number {
  return ((a % 360) + 360) % 360;
}

// SunCalc v2 returns azimuth north-based clockwise in degrees (0=N, 90=E, 180=S, 270=W),
// which matches the chart's toXY convention, so only a 0–360 clamp is needed.
function chartAzimuth(degrees: number): number {
  return ((degrees % 360) + 360) % 360;
}

export interface LabeledStar {
  name: string;
  mag: number;
  azimuth: number;
  altitude: number;
  x: number;
  y: number;
}

export interface LabelPlacement {
  name: string;
  x: number;
  y: number;
  anchor: "start" | "end" | "middle";
  sourceX: number;
  sourceY: number;
  adjusted: boolean;
  lineToX: number;
  lineToY: number;
}

export interface LabelObstacles {
  arcSegments?: { x: number; y: number }[][];
  circles?: { x: number; y: number; radius: number }[];
}

const LABEL_FONT_SIZE = 9;
const LABEL_CHAR_W = 7;
const LABEL_HEIGHT = 12;
const PADDING = 4;

function labelWidth(text: string): number {
  return text.length * LABEL_CHAR_W + PADDING * 2;
}

function labelBox(
  x: number,
  y: number,
  anchor: string,
  w: number,
  h: number,
): { x1: number; y1: number; x2: number; y2: number } {
  let x1: number;
  if (anchor === "end") {
    x1 = x - w;
  } else if (anchor === "middle") {
    x1 = x - w / 2;
  } else {
    x1 = x;
  }
  const y1 = y - h / 2;
  return { x1, y1, x2: x1 + w, y2: y1 + h };
}

function boxesOverlap(
  a: ReturnType<typeof labelBox>,
  b: ReturnType<typeof labelBox>,
): boolean {
  return a.x1 < b.x2 && a.x2 > b.x1 && a.y1 < b.y2 && a.y2 > b.y1;
}

function segmentIntersectsBox(
  ax: number,
  ay: number,
  bx: number,
  by: number,
  box: ReturnType<typeof labelBox>,
): boolean {
  let t0 = 0;
  let t1 = 1;
  const dx = bx - ax;
  const dy = by - ay;
  const edges = [
    [-dx, ax - box.x1],
    [dx, box.x2 - ax],
    [-dy, ay - box.y1],
    [dy, box.y2 - ay],
  ];

  for (const [p, q] of edges) {
    if (p === 0) {
      if (q < 0) return false;
      continue;
    }
    const r = q / p;
    if (p < 0) {
      if (r > t1) return false;
      if (r > t0) t0 = r;
    } else {
      if (r < t0) return false;
      if (r < t1) t1 = r;
    }
  }
  return true;
}

function boxHitsObstacle(
  box: ReturnType<typeof labelBox>,
  obstacles: LabelObstacles | undefined,
): boolean {
  if (!obstacles) return false;
  const margin = 3;
  const expanded = {
    x1: box.x1 - margin,
    y1: box.y1 - margin,
    x2: box.x2 + margin,
    y2: box.y2 + margin,
  };

  for (const segment of obstacles.arcSegments ?? []) {
    for (let i = 1; i < segment.length; i += 1) {
      const from = segment[i - 1];
      const to = segment[i];
      if (segmentIntersectsBox(from.x, from.y, to.x, to.y, expanded)) {
        return true;
      }
    }
  }

  for (const circle of obstacles.circles ?? []) {
    const nearestX = Math.max(expanded.x1, Math.min(circle.x, expanded.x2));
    const nearestY = Math.max(expanded.y1, Math.min(circle.y, expanded.y2));
    const dx = nearestX - circle.x;
    const dy = nearestY - circle.y;
    if (dx * dx + dy * dy <= (circle.radius + margin) ** 2) return true;
  }

  return false;
}

function boxInsideChart(box: ReturnType<typeof labelBox>): boolean {
  const radius = CHART_RH - 3;
  const corners = [
    [box.x1, box.y1],
    [box.x2, box.y1],
    [box.x1, box.y2],
    [box.x2, box.y2],
  ];
  return corners.every(([x, y]) => {
    const dx = x - CHART_CX;
    const dy = y - CHART_CY;
    return dx * dx + dy * dy <= radius * radius;
  });
}

function nearestBoxEdge(
  anchor: string,
  lx: number,
  ly: number,
  text: string,
  sx: number,
  sy: number,
): { x: number; y: number } {
  const w = labelWidth(text);
  const box = labelBox(lx, ly, anchor, w, LABEL_HEIGHT);
  return {
    x: Math.max(box.x1, Math.min(sx, box.x2)),
    y: Math.max(box.y1, Math.min(sy, box.y2)),
  };
}

function anchorPriority(
  preferred: "start" | "end" | "middle",
): ("start" | "end" | "middle")[] {
  const others = ["start", "end", "middle"] as const;
  return [preferred, ...others.filter((a) => a !== preferred)];
}

export function computeLabelPlacements(
  stars: LabeledStar[],
  obstacles?: LabelObstacles,
): LabelPlacement[] {
  if (stars.length === 0) return [];

  const candidates: (LabelPlacement & {
    mag: number;
    nx: number;
    ny: number;
    baseR: number;
  })[] = stars.map((s) => {
    const dx = s.x - CHART_CX;
    const dy = s.y - CHART_CY;
    const dist = Math.sqrt(dx * dx + dy * dy);

    let nx: number, ny: number;
    if (dist < 0.5) {
      const a = (s.azimuth * Math.PI) / 180;
      nx = Math.sin(a);
      ny = -Math.cos(a);
    } else {
      nx = dx / dist;
      ny = dy / dist;
    }

    let anchor: "start" | "end" | "middle";
    if (Math.abs(nx) > Math.abs(ny)) {
      anchor = nx > 0 ? "end" : "start";
    } else {
      anchor = "middle";
    }

    const baseR = Math.min(dist + 10, CHART_RH - 4);

    return {
      name: s.name,
      mag: s.mag,
      nx,
      ny,
      baseR,
      x: CHART_CX + nx * baseR,
      y: CHART_CY + ny * baseR,
      anchor,
      sourceX: s.x,
      sourceY: s.y,
      adjusted: false,
      lineToX: s.x,
      lineToY: s.y,
    };
  });

  candidates.sort((a, b) => a.mag - b.mag);

  const placed: LabelPlacement[] = [];
  const placedBoxes: ReturnType<typeof labelBox>[] = [];

  for (const c of candidates) {
    let best: LabelPlacement | null = null;

    const radiusOffsets = [0, -14, 14, -28, 28, -42, 42, -56, 56];
    for (const dr of radiusOffsets) {
      const r = c.baseR + dr;
      if (r < 10 || r > CHART_RH) continue;
      if (r > CHART_RH + 6) break;
      const bx = CHART_CX + c.nx * r;
      const by = CHART_CY + c.ny * r;

      for (const anchor of anchorPriority(c.anchor)) {
        const w = labelWidth(c.name);
        const box = labelBox(bx, by, anchor, w, LABEL_HEIGHT);

        const overlaps = placedBoxes.some((pb) => boxesOverlap(box, pb));
          if (!overlaps && boxInsideChart(box) && !boxHitsObstacle(box, obstacles)) {
            const n = nearestBoxEdge(anchor, bx, by, c.name, c.sourceX, c.sourceY);
            best = {
              name: c.name,
              x: bx,
              y: by,
              anchor,
              sourceX: c.sourceX,
              sourceY: c.sourceY,
              adjusted: Math.abs(bx - c.x) > 0.5 || Math.abs(by - c.y) > 0.5 || anchor !== c.anchor,
              lineToX: n.x,
              lineToY: n.y,
            };
          placedBoxes.push(box);
          break;
        }
      }
      if (best) break;
    }

    if (!best) {
      for (const sweep of [-10, 10, -20, 20, -30, 30]) {
        const sweepRad = (sweep * Math.PI) / 180;
        const snx = c.nx * Math.cos(sweepRad) - c.ny * Math.sin(sweepRad);
        const sny = c.nx * Math.sin(sweepRad) + c.ny * Math.cos(sweepRad);
        const r = Math.min(c.baseR + 14, CHART_RH - 8);

        const bx = CHART_CX + snx * r;
        const by = CHART_CY + sny * r;

        for (const anchor of anchorPriority(c.anchor)) {
          const w = labelWidth(c.name);
          const box = labelBox(bx, by, anchor, w, LABEL_HEIGHT);

          const overlaps = placedBoxes.some((pb) => boxesOverlap(box, pb));
          if (!overlaps && boxInsideChart(box) && !boxHitsObstacle(box, obstacles)) {
            const n = nearestBoxEdge(anchor, bx, by, c.name, c.sourceX, c.sourceY);
            best = {
              name: c.name,
              x: bx,
              y: by,
              anchor,
              sourceX: c.sourceX,
              sourceY: c.sourceY,
              adjusted: true,
              lineToX: n.x,
              lineToY: n.y,
            };
            placedBoxes.push(box);
            break;
          }
        }
        if (best) break;
      }
    }

    if (!best) {
      const box = labelBox(c.x, c.y, c.anchor, labelWidth(c.name), LABEL_HEIGHT);
      placedBoxes.push(box);
      best = {
        name: c.name,
        x: c.x,
        y: c.y,
        anchor: c.anchor,
        sourceX: c.sourceX,
        sourceY: c.sourceY,
        adjusted: false,
        lineToX: c.sourceX,
        lineToY: c.sourceY,
      };
    }

    placed.push(best);
  }

  return placed;
}
