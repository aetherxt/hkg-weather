"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import {
  CurrentWeatherReport,
  EnvironmentalConditions,
} from "@/components/current-weather-report";
import { RainfallDetailPanel } from "@/components/rainfall-detail-panel";
import { TemperatureDetailPanel } from "@/components/temperature-detail-panel";
import { WarningsDetailPanel } from "@/components/warnings-detail-panel";
import type { WeatherDetailSection } from "@/components/weather-detail-sections";
import { WeatherWarnings } from "@/components/weather-warnings";
import type { InitialWeatherState } from "@/lib/weather/initial";
import { currentWeatherViewModel } from "@/lib/weather/view-models";
import { weatherClient } from "@/lib/weather/client";
import type {
  ReadyWeatherSection,
  WeatherSectionState,
} from "@/lib/weather/state";
import {
  activeWarnings,
  warningDisplayName,
  warningSummaryHeadline,
} from "@/lib/weather";
import type {
  CurrentWeather,
  LamppostReading,
  LocalForecast,
  StationRainfallResponse,
  TemperatureReading,
  Warnings,
  WindReading,
} from "@/lib/weather/types";

function warningsDetailBody(warnings: Warnings): string {
  return activeWarnings(warnings.summary)
    .map((w) => warningDisplayName(w))
    .join(", ");
}

const staticDetailSections: Array<{
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
    id: "uv",
    label: "Sun",
    headline: "Sunrise & Sunset",
    body: "Today's sunrise and sunset times.",
  },
];

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
    setActiveSection((prev) => {
      if (prev === section) return prev;
      setAnimationIteration((iteration) => iteration + 1);
      return section;
    });
  }, []);

  function liveSection<Data>(section: WeatherSectionState<Data>) {
    return section.status === "ready" || section.status === "stale"
      ? section
      : null;
  }

  const [currentSection, setCurrentSection] = useState(() =>
    liveSection(initialWeather.current),
  );
  const [regionalTemperature, setRegionalTemperature] = useState(() =>
    liveSection(initialWeather.regionalTemperature),
  );
  const [regionalWind, setRegionalWind] = useState(() =>
    liveSection(initialWeather.regionalWind),
  );
  const [lampposts, setLampposts] = useState(() =>
    liveSection(initialWeather.lampposts),
  );
  const [stationRainfall, setStationRainfall] = useState(() =>
    liveSection(initialWeather.stationRainfall),
  );
  const [localForecast, setLocalForecast] = useState(() =>
    liveSection(initialWeather.localForecast),
  );
  const [warningsSection, setWarningsSection] = useState(() =>
    liveSection(initialWeather.warnings),
  );

  const warnings = warningsSection?.data.summary ?? null;
  const warningsData = warningsSection?.data ?? null;
  const hasWarnings = warnings
    ? Object.values(warnings).some((w) => w.actionCode !== "CANCEL")
    : false;
  const warningsDetailSection = hasWarnings && warningsData
    ? [{
        id: "warnings" as const,
        label: "Warnings",
        headline: warningSummaryHeadline(warningsData.summary),
        body: warningsDetailBody(warningsData),
      }]
    : [];
  const availableDetailSections = [
    ...staticDetailSections.slice(0, 2),
    ...warningsDetailSection,
    ...staticDetailSections.slice(2),
  ];
  const activeDetail = availableDetailSections.find(
    (detail) => detail.id === activeSection,
  );

  useLayoutEffect(() => {
    const nav = miniNavRef.current;
    if (!nav || !activeDetail) {
      nav?.style.removeProperty("--active-opacity");
      return;
    }

    const activeButton = nav.querySelector<HTMLElement>(
      `[data-weather-detail="${activeDetail.id}"]`,
    );
    if (!activeButton) {
      nav.style.removeProperty("--active-opacity");
      return;
    }

    nav.style.setProperty("--active-left", `${activeButton.offsetLeft}px`);
    nav.style.setProperty("--active-width", `${activeButton.offsetWidth}px`);
    nav.style.setProperty("--active-opacity", "1");
  }, [activeDetail]);

  useEffect(() => {
    if (!activeDetail && activeSection) {
      setActiveSection(null);
    }
  }, [activeDetail, activeSection]);

  useEffect(() => {
    const interval = setInterval(async () => {
      const results = await Promise.allSettled([
        weatherClient.getCurrentWeather(),
        weatherClient.getWarnings(),
        weatherClient.getRegionalTemperature(),
        weatherClient.getRegionalWind(),
        weatherClient.getLampposts(),
        weatherClient.getStationRainfall(),
        weatherClient.getLocalForecast(),
      ]);

      const [current, warnings, temp, wind, lamp, station, forecast] = results;

      if (current.status === "fulfilled") {
        const { data, meta } = current.value;
        setCurrentSection({ status: "ready", data, meta, sourceUpdatedAt: meta.sourceUpdatedAt, fetchedAt: meta.fetchedAt });
      }
      if (warnings.status === "fulfilled") {
        const { data, meta } = warnings.value;
        setWarningsSection({ status: "ready", data, meta, sourceUpdatedAt: meta.sourceUpdatedAt, fetchedAt: meta.fetchedAt });
      }
      if (temp.status === "fulfilled") {
        const { data, meta } = temp.value;
        setRegionalTemperature({ status: "ready", data, meta, sourceUpdatedAt: meta.sourceUpdatedAt, fetchedAt: meta.fetchedAt });
      }
      if (wind.status === "fulfilled") {
        const { data, meta } = wind.value;
        setRegionalWind({ status: "ready", data, meta, sourceUpdatedAt: meta.sourceUpdatedAt, fetchedAt: meta.fetchedAt });
      }
      if (lamp.status === "fulfilled") {
        const { data, meta } = lamp.value;
        setLampposts({ status: "ready", data, meta, sourceUpdatedAt: meta.sourceUpdatedAt, fetchedAt: meta.fetchedAt });
      }
      if (station.status === "fulfilled") {
        const { data, meta } = station.value;
        setStationRainfall({ status: "ready", data, meta, sourceUpdatedAt: meta.sourceUpdatedAt, fetchedAt: meta.fetchedAt });
      }
      if (forecast.status === "fulfilled") {
        const { data, meta } = forecast.value;
        setLocalForecast({ status: "ready", data, meta, sourceUpdatedAt: meta.sourceUpdatedAt, fetchedAt: meta.fetchedAt });
      }
    }, 60_000);
    return () => clearInterval(interval);
  }, []);

  const vm = currentSection
    ? currentWeatherViewModel(currentSection.data)
    : null;
  const currentUpdatedAt = currentSection
    ? (currentSection.sourceUpdatedAt ?? currentSection.fetchedAt)
    : null;

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
                  regionalTemperature={regionalTemperature ?? initialWeather.regionalTemperature}
                  lampposts={lampposts ?? initialWeather.lampposts}
                  regionalWind={regionalWind ?? initialWeather.regionalWind}
                />
              ) : activeDetail.id === "rainfall-wind" ? (
                <RainfallDetailPanel
                  rainfallReadings={rainfallReadings}
                  stationRainfall={stationRainfall ?? initialWeather.stationRainfall}
                  localForecast={localForecast ?? initialWeather.localForecast}
                />
              ) : activeDetail.id === "warnings" && warningsData ? (
                <WarningsDetailPanel warnings={warningsData} />
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
