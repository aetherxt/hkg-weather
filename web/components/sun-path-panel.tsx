"use client";

import { useEffect, useMemo, useState } from "react";

import type { AstronomicalTimes } from "@/lib/weather/types";

const SAMPLE_SUNRISE = "05:52";
const SAMPLE_SUNSET = "19:09";
const CHART = {
  apexY: 94,
  horizonY: 242,
  sunriseX: 78,
  sunsetX: 562,
};

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
}: {
  astronomical: AstronomicalTimes | null;
  initialNow: string;
}) {
  const sunrise = astronomical?.sunrise || SAMPLE_SUNRISE;
  const sunset = astronomical?.sunset || SAMPLE_SUNSET;
  const [now, setNow] = useState(() => new Date(initialNow));

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

  const curvePath = sampledPath(24, 616);

  return (
    <section
      className="sun-path-panel"
      data-using-sample-times={astronomical ? undefined : "true"}
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
          <clipPath id="sun-path-above-horizon">
            <rect x="0" y="0" width="640" height={CHART.horizonY} />
          </clipPath>
          <clipPath id="sun-path-below-horizon">
            <rect
              x="0"
              y={CHART.horizonY}
              width="640"
              height={350 - CHART.horizonY}
            />
          </clipPath>
        </defs>

        <rect className="sun-path-backdrop" x="0" y="0" width="640" height="350" />

        <g className="sun-path-cloud sun-path-cloud-one" aria-hidden="true">
          <ellipse cx="116" cy="91" rx="34" ry="11" />
          <circle cx="99" cy="86" r="13" />
          <circle cx="119" cy="78" r="18" />
          <circle cx="140" cy="87" r="13" />
        </g>
        <g className="sun-path-cloud sun-path-cloud-two" aria-hidden="true">
          <ellipse cx="465" cy="121" rx="40" ry="12" />
          <circle cx="445" cy="115" r="14" />
          <circle cx="468" cy="105" r="20" />
          <circle cx="493" cy="116" r="14" />
        </g>
        <g className="sun-path-cloud sun-path-cloud-three" aria-hidden="true">
          <ellipse cx="350" cy="63" rx="25" ry="8" />
          <circle cx="338" cy="59" r="9" />
          <circle cx="352" cy="53" r="13" />
          <circle cx="367" cy="59" r="9" />
        </g>

        <line
          className="sun-path-horizon"
          x1="0"
          y1={CHART.horizonY}
          x2="640"
          y2={CHART.horizonY}
        />
        <path
          className="sun-path-curve sun-path-curve-above"
          d={curvePath}
          clipPath="url(#sun-path-above-horizon)"
        />
        <path
          className="sun-path-curve sun-path-curve-below"
          d={curvePath}
          clipPath="url(#sun-path-below-horizon)"
        />

        {sunState.isDaylight ? (
          <g
            className="sun-path-sun"
            transform={`translate(${sunState.x} ${sunState.y})`}
          >
            <text className="sun-current-time" textAnchor="middle" y="-31">
              {displayTime(now)}
            </text>
            <circle className="sun-path-sun-disc" r="20" />
            <circle className="sun-path-sun-face" r="15" />
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
