"use client";

import { useCallback, useLayoutEffect, useRef, useState } from "react";

import {
  CurrentWeatherReport,
  EnvironmentalConditions,
} from "@/components/current-weather-report";
import { RainfallDetailPanel } from "@/components/rainfall-detail-panel";
import { TemperatureDetailPanel } from "@/components/temperature-detail-panel";
import type { WeatherDetailSection } from "@/components/weather-detail-sections";
import { WeatherWarnings } from "@/components/weather-warnings";
import type { InitialWeatherState } from "@/lib/weather/initial";
import { currentWeatherViewModel } from "@/lib/weather/view-models";
import type { WarningSummary } from "@/lib/weather/types";

const detailSections: Array<{
  id: WeatherDetailSection;
  label: string;
  headline: string;
  body: string;
}> = [
  {
    id: "temperature",
    label: "Temperature",
    headline: "Regional observations",
    body: "",
  },
  {
    id: "rainfall-wind",
    label: "Rainfall",
    headline: "Rainfall & Wind",
    body: "",
  },
  {
    id: "warnings",
    label: "Warnings",
    headline: "2 warnings in force",
    body: "A Red Rainstorm Warning and the Strong Monsoon Signal are currently active.",
  },
  {
    id: "uv",
    label: "Sun",
    headline: "Sunrise & Sunset",
    body: "Today's sunrise and sunset times.",
  },
];

function warningsSummary(
  section: InitialWeatherState["warnings"],
): WarningSummary | null {
  if (section.status === "ready" || section.status === "stale") {
    return section.data.summary;
  }
  return null;
}

export function WeatherDashboard({
  initialWeather,
}: {
  initialWeather: InitialWeatherState;
}) {
  const [activeSection, setActiveSection] =
    useState<WeatherDetailSection | null>(null);
  const [animationIteration, setAnimationIteration] = useState(0);
  const miniNavRef = useRef<HTMLElement>(null);

  const selectSection = useCallback((section: WeatherDetailSection) => {
    setActiveSection(section);
    setAnimationIteration((iteration) => iteration + 1);
  }, []);

  useLayoutEffect(() => {
    const nav = miniNavRef.current;
    if (!nav || !activeSection) {
      nav?.style.removeProperty("--active-opacity");
      return;
    }

    const activeButton = nav.querySelector<HTMLElement>(
      `[data-weather-detail="${activeSection}"]`,
    );
    if (!activeButton) {
      nav.style.removeProperty("--active-opacity");
      return;
    }

    nav.style.setProperty("--active-left", `${activeButton.offsetLeft}px`);
    nav.style.setProperty("--active-width", `${activeButton.offsetWidth}px`);
    nav.style.setProperty("--active-opacity", "1");
  }, [activeSection]);

  const currentSection = initialWeather.current.status === "ready" ||
    initialWeather.current.status === "stale"
    ? initialWeather.current
    : null;
  const vm = currentSection ? currentWeatherViewModel(currentSection.data) : null;
  const currentUpdatedAt = currentSection
    ? (currentSection.sourceUpdatedAt ?? currentSection.fetchedAt)
    : null;

  const warningsSection = initialWeather.warnings.status === "ready" ||
    initialWeather.warnings.status === "stale"
    ? initialWeather.warnings
    : null;
  const warnings = warningsSummary(initialWeather.warnings);
  const warningsUpdatedAt = warningsSection
    ? (warningsSection.sourceUpdatedAt ?? warningsSection.fetchedAt)
    : null;
  const astronomicalSection = initialWeather.astronomical.status === "ready" ||
    initialWeather.astronomical.status === "stale"
    ? initialWeather.astronomical
    : null;
  const astronomical = astronomicalSection?.data ?? null;

  const rainfallReadings =
    currentSection?.data.rainfall?.data ?? [];

  const hasWarnings = warnings
    ? Object.values(warnings).some((w) => w.actionCode !== "CANCEL")
    : false;
  const availableDetailSections = hasWarnings
    ? detailSections
    : detailSections.filter((detail) => detail.id !== "warnings");

  const activeDetail = availableDetailSections.find(
    (detail) => detail.id === activeSection,
  );

  return (
    <main
      className="weather-page weather-dashboard"
      data-active-section={activeSection ?? undefined}
    >
      <div className="weather-left-column">
        <CurrentWeatherReport
          temperature={vm?.temperature ?? null}
          condition={vm?.condition ?? null}
          humidity={vm?.humidity ?? null}
          rainfall={vm?.rainfall ?? null}
          updatedAt={currentUpdatedAt}
          activeSection={activeSection}
          onSelectSection={selectSection}
        />

        <WeatherWarnings
          warnings={warnings ?? {}}
          updatedAt={warningsUpdatedAt}
          activeSection={activeSection}
          onSelectSection={selectSection}
        />

        <EnvironmentalConditions
          uvIndex={vm?.uvIndex ?? null}
          uvLevel={vm?.uvLevel ?? null}
          astronomical={astronomical}
          activeSection={activeSection}
          onSelectSection={selectSection}
        />
      </div>

      <aside className="weather-detail-dock" aria-label="Weather details">
        <nav
          className="weather-mini-nav"
          ref={miniNavRef}
          aria-label="Weather detail navigation"
          role="tablist"
        >
          {availableDetailSections.map((detail) => {
            const isActive = activeSection === detail.id;

            return (
              <button
                className="weather-mini-nav-link"
                data-testid={`weather-detail-${detail.id}`}
                data-weather-detail={detail.id}
                data-active={isActive ? "true" : undefined}
                aria-controls={`weather-detail-${detail.id}-content`}
                aria-selected={isActive}
                onClick={() => selectSection(detail.id)}
                role="tab"
                type="button"
                key={detail.id}
              >
                {detail.label}
              </button>
            );
          })}
        </nav>

        <div className="weather-mini-panel-stage" aria-live="polite">
          {activeDetail ? (
            <section
              className="weather-mini-panel"
              data-detail={activeDetail.id}
              id={`weather-detail-${activeDetail.id}-content`}
              role="tabpanel"
              key={`${activeDetail.id}-${animationIteration}`}
            >
              {activeDetail.id === "temperature" ? (
                <TemperatureDetailPanel
                  regionalTemperature={initialWeather.regionalTemperature}
                  lampposts={initialWeather.lampposts}
                  regionalWind={initialWeather.regionalWind}
                />
              ) : activeDetail.id === "rainfall-wind" ? (
                <RainfallDetailPanel
                  rainfallReadings={rainfallReadings}
                  stationRainfall={initialWeather.stationRainfall}
                />
              ) : (
                <>
                  <p className="weather-mini-panel-kicker">
                    {activeDetail.label}
                  </p>
                  <h2 className="weather-mini-panel-title">
                    {activeDetail.headline}
                  </h2>
                  <p className="weather-mini-panel-copy">
                    {activeDetail.body}
                  </p>
                </>
              )}
            </section>
          ) : null}
        </div>
      </aside>
    </main>
  );
}
