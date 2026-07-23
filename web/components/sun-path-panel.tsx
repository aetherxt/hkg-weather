"use client";

import { useEffect, useMemo, useState } from "react";

import { getConditionTone } from "@/lib/weather/condition-tone";
import type { AstronomicalTimes } from "@/lib/weather/types";
import { getUvTone } from "@/lib/weather/uv-tone";

const SAMPLE_SUNRISE = "05:52";
const SAMPLE_SUNSET = "19:09";
const CHART = {
  apexY: 94,
  horizonY: 242,
  sunriseX: 78,
  sunsetX: 562,
};

const CLOUD_PATHS = {
  rounded:
    "M 17 60 C 8 60 0 52 0 42 C 0 32 8 24 18 24 C 23 10 35 0 50 0 C 65 0 77 11 81 25 C 92 26 100 34 100 45 C 100 53 94 60 85 60 Z",
  layered:
    "M 13 60 C 6 60 0 53 0 45 C 0 37 6 30 14 29 C 17 20 24 14 34 14 C 38 5 47 0 57 0 C 69 0 78 8 80 19 C 91 20 100 29 100 41 C 100 52 92 60 82 60 Z",
  compact:
    "M 16 60 C 7 60 0 53 0 44 C 0 35 7 28 16 27 C 20 20 27 16 35 17 C 40 6 49 0 60 0 C 73 0 83 10 84 23 C 93 25 100 33 100 43 C 100 52 93 60 84 60 Z",
} as const;

function FlatCloud({
  x,
  y,
  width,
  height,
  variant,
}: {
  x: number;
  y: number;
  width: number;
  height: number;
  variant: keyof typeof CLOUD_PATHS;
}) {
  return (
    <path
      d={CLOUD_PATHS[variant]}
      transform={`translate(${x} ${y}) scale(${width / 100} ${height / 60})`}
    />
  );
}

function RainCluster({
  x,
  y,
  width,
  count = 5,
}: {
  x: number;
  y: number;
  width: number;
  count?: number;
}) {
  return (
    <>
      {Array.from({ length: count }, (_, index) => {
        const dropX = x + ((index + 0.5) * width) / count;
        const dropY = y + (index % 3) * 7;

        return (
          <line
            className="sun-path-rain-drop"
            x1={dropX}
            y1={dropY}
            x2={dropX - 4}
            y2={dropY + 14}
            style={{ animationDelay: `${-((index * 137) % 700)}ms` }}
            key={index}
          />
        );
      })}
    </>
  );
}

function rainDropCount(rainfall: number | null): number {
  if (rainfall === null || rainfall <= 0) return 0;
  if (rainfall < 1) return 3;
  if (rainfall < 2.5) return 4;
  if (rainfall < 5) return 6;
  if (rainfall < 10) return 8;
  if (rainfall < 30) return 10;
  return 12;
}

function timeToMinutes(value: string): number | null {
  const match = /^(\d{1,2}):(\d{2})/.exec(value.trim());
  if (!match) return null;

  const hours = Number(match[1]);
  const minutes = Number(match[2]);
  if (hours > 23 || minutes > 59) return null;
  return hours * 60 + minutes;
}

function sunY(x: number): number {
  const midpoint = (CHART.sunriseX + CHART.sunsetX) / 2;
  const halfDayWidth = (CHART.sunsetX - CHART.sunriseX) / 2;
  const normalizedX = (x - midpoint) / halfDayWidth;

  return (
    CHART.apexY +
    (CHART.horizonY - CHART.apexY) * normalizedX * normalizedX
  );
}

function sampledPath(fromX: number, toX: number, step = 8): string {
  const points: Array<[number, number]> = [];
  for (let x = fromX; x < toX; x += step) {
    points.push([x, sunY(x)]);
  }
  points.push([toX, sunY(toX)]);

  return points
    .map(([x, y], index) => `${index === 0 ? "M" : "L"} ${x} ${y}`)
    .join(" ");
}

function minuteOfDay(date: Date): number {
  return date.getHours() * 60 + date.getMinutes() + date.getSeconds() / 60;
}

function displayTime(date: Date): string {
  return `${String(date.getHours()).padStart(2, "0")}:${String(
    date.getMinutes(),
  ).padStart(2, "0")}`;
}

export function SunPathPanel({
  astronomical,
  initialNow,
  condition,
  rainfall,
  uvIndex,
  thunderstormWarningActive,
}: {
  astronomical: AstronomicalTimes | null;
  initialNow: string;
  condition: string | null;
  rainfall: number | null;
  uvIndex: number | null;
  thunderstormWarningActive: boolean;
}) {
  const sunrise = astronomical?.sunrise || SAMPLE_SUNRISE;
  const sunset = astronomical?.sunset || SAMPLE_SUNSET;
  const [now, setNow] = useState(() => new Date(initialNow));
  const conditionTone = condition ? getConditionTone(condition) : "neutral";
  const normalizedCondition = condition?.toLowerCase() ?? "";
  const showThunder = thunderstormWarningActive;
  const showRain = rainfall !== null && rainfall > 0;
  const showStormClouds = showRain || showThunder;
  const showClearGradient =
    !showStormClouds &&
    (conditionTone === "sunny" ||
      conditionTone === "neutral" ||
      normalizedCondition.includes("sun") ||
      normalizedCondition.includes("fine") ||
      normalizedCondition.includes("clear"));
  const rainDropsPerQuarter = rainDropCount(rainfall);

  useEffect(() => {
    const interval = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(interval);
  }, []);

  const sunState = useMemo(() => {
    const sunriseMinute = timeToMinutes(sunrise) ?? timeToMinutes(SAMPLE_SUNRISE)!;
    const sunsetMinute = timeToMinutes(sunset) ?? timeToMinutes(SAMPLE_SUNSET)!;
    const currentMinute = minuteOfDay(now);
    const rawProgress =
      (currentMinute - sunriseMinute) / (sunsetMinute - sunriseMinute);
    const progress = Math.min(1, Math.max(0, rawProgress));
    const x =
      CHART.sunriseX +
      progress * (CHART.sunsetX - CHART.sunriseX);

    return {
      isDaylight: rawProgress >= 0 && rawProgress <= 1,
      x,
      y: sunY(x),
    };
  }, [now, sunrise, sunset]);

  const curvePath = sampledPath(CHART.sunriseX, CHART.sunsetX);

  return (
    <section
      className="sun-path-panel"
      data-using-sample-times={astronomical ? undefined : "true"}
      data-weather-state={conditionTone}
      data-rainfall={rainfall ?? undefined}
      data-rain-drops={showRain ? rainDropsPerQuarter * 4 : undefined}
      data-thunderstorm-warning={showThunder ? "active" : undefined}
      aria-label="Sunrise and sunset"
    >
      <p className="sun-path-caption">Sunpath</p>
      <svg
        className="sun-path-chart"
        viewBox="0 0 640 350"
        role="img"
        aria-label={`Sunrise at ${sunrise}, sunset at ${sunset}`}
      >
        <defs>
          <linearGradient id="sun-horizon-upper" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#467da3" stopOpacity="0" />
            <stop offset="1" stopColor="#245d86" stopOpacity="0.44" />
          </linearGradient>
          <linearGradient id="sun-horizon-clear" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#f2d87a" stopOpacity="0" />
            <stop offset="0.45" stopColor="#edcf69" stopOpacity="0.06" />
            <stop offset="1" stopColor="#dfb63d" stopOpacity="0.28" />
          </linearGradient>
          <linearGradient id="sun-horizon-lower" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#1d5f91" stopOpacity="0.26" />
            <stop offset="1" stopColor="#17466c" stopOpacity="0.04" />
          </linearGradient>
          <filter id="sun-path-soft-glow" x="-20%" y="-40%" width="140%" height="180%">
            <feGaussianBlur stdDeviation="1.5" />
          </filter>
          <filter id="sun-disc-soft-glow" x="-100%" y="-100%" width="300%" height="300%">
            <feGaussianBlur stdDeviation="3" />
          </filter>
        </defs>

        {showRain ? (
          <rect
            className="sun-horizon-gradient"
            x="0"
            y="0"
            width="640"
            height={CHART.horizonY}
            fill="url(#sun-horizon-upper)"
          />
        ) : null}
        {showClearGradient ? (
          <rect
            className="sun-horizon-gradient"
            x="0"
            y="0"
            width="640"
            height={CHART.horizonY}
            fill="url(#sun-horizon-clear)"
          />
        ) : null}
        <rect
          className="sun-horizon-gradient"
          x="0"
          y={CHART.horizonY}
          width="640"
          height={350 - CHART.horizonY}
          fill="url(#sun-horizon-lower)"
        />

        {showThunder ? (
          <g className="sun-path-thunder" aria-hidden="true">
            <path
              className="sun-path-thunder-bolt sun-path-thunder-bolt-one"
              d="M 108 66 L 83 108 H 101 L 87 154 L 128 98 H 108 L 124 66 Z"
            />
            <path
              className="sun-path-thunder-bolt sun-path-thunder-bolt-two"
              d="M 536 78 L 517 111 H 531 L 520 147 L 552 103 H 537 L 549 78 Z"
            />
            <path
              className="sun-path-thunder-bolt sun-path-thunder-bolt-three"
              d="M 332 44 L 295 107 H 322 L 300 177 L 360 96 H 332 L 354 44 Z"
            />
          </g>
        ) : null}

        {showStormClouds ? (
          <g className="sun-path-rain-clouds" aria-hidden="true">
            <FlatCloud
              x={54}
              y={36}
              width={104}
              height={58}
              variant="layered"
            />
            <FlatCloud
              x={268}
              y={18}
              width={118}
              height={67}
              variant="rounded"
            />
            <FlatCloud
              x={486}
              y={42}
              width={98}
              height={55}
              variant="compact"
            />
          </g>
        ) : conditionTone === "cloudy" ? (
          <>
            <g className="sun-path-cloud sun-path-cloud-one" aria-hidden="true">
              <FlatCloud
                x={82}
                y={60}
                width={69}
                height={36}
                variant="rounded"
              />
            </g>
            <g className="sun-path-cloud sun-path-cloud-two" aria-hidden="true">
              <FlatCloud
                x={425}
                y={84}
                width={80}
                height={43}
                variant="layered"
              />
            </g>
            <g className="sun-path-cloud sun-path-cloud-three" aria-hidden="true">
              <FlatCloud
                x={325}
                y={40}
                width={52}
                height={28}
                variant="compact"
              />
            </g>
          </>
        ) : null}

        {showRain ? (
          <g className="sun-path-rain" aria-hidden="true">
            <g className="sun-path-rain-field">
              <RainCluster
                x={0}
                y={114}
                width={160}
                count={rainDropsPerQuarter}
              />
              <RainCluster
                x={160}
                y={114}
                width={160}
                count={rainDropsPerQuarter}
              />
              <RainCluster
                x={320}
                y={114}
                width={160}
                count={rainDropsPerQuarter}
              />
              <RainCluster
                x={480}
                y={114}
                width={160}
                count={rainDropsPerQuarter}
              />
            </g>
          </g>
        ) : null}

        <line
          className="sun-path-horizon"
          x1="0"
          y1={CHART.horizonY}
          x2="640"
          y2={CHART.horizonY}
        />
        <g className="sun-path-glow" aria-hidden="true">
          <path className="sun-path-glow-day" d={curvePath} />
          <path
            className="sun-path-glow-limit"
            d={`M ${CHART.sunriseX} ${CHART.horizonY} C 59 262, 31 277, 0 279`}
          />
          <path
            className="sun-path-glow-limit"
            d={`M ${CHART.sunsetX} ${CHART.horizonY} C 581 262, 609 277, 640 279`}
          />
        </g>
        <path
          className="sun-path-curve sun-path-curve-day"
          d={curvePath}
        />
        <path
          className="sun-path-curve sun-path-limit"
          d={`M ${CHART.sunriseX} ${CHART.horizonY} C 59 262, 31 277, 0 279`}
        />
        <path
          className="sun-path-curve sun-path-limit"
          d={`M ${CHART.sunsetX} ${CHART.horizonY} C 581 262, 609 277, 640 279`}
        />

        {sunState.isDaylight ? (
          <g
            className="sun-path-sun"
            data-uv-tone={uvIndex !== null ? getUvTone(uvIndex) : undefined}
            transform={`translate(${sunState.x} ${sunState.y})`}
          >
            <text className="sun-current-time" textAnchor="middle" y="-31">
              {displayTime(now)}
            </text>
            <circle className="sun-path-sun-glow" r="25" />
            <circle className="sun-path-sun-disc" r="20" />
            <text
              className="sun-path-sun-uv"
              textAnchor="middle"
              dominantBaseline="central"
              aria-label={
                uvIndex !== null ? `UV index ${uvIndex}` : "UV index unavailable"
              }
            >
              {uvIndex !== null
                ? Number.isInteger(uvIndex)
                  ? uvIndex.toFixed(0)
                  : uvIndex.toFixed(1)
                : "–"}
            </text>
          </g>
        ) : null}

        <g className="sun-time-label" transform={`translate(${CHART.sunriseX} 306)`}>
          <text className="sun-time-name" textAnchor="middle" y="0">
            Sunrise
          </text>
          <text className="sun-time-value" textAnchor="middle" y="25">
            {sunrise}
          </text>
        </g>
        <g className="sun-time-label" transform={`translate(${CHART.sunsetX} 306)`}>
          <text className="sun-time-name" textAnchor="middle" y="0">
            Sunset
          </text>
          <text className="sun-time-value" textAnchor="middle" y="25">
            {sunset}
          </text>
        </g>
      </svg>
    </section>
  );
}
