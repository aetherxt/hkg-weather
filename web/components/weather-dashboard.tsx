"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import {
  CurrentWeatherReport,
  EnvironmentalConditions,
} from "@/components/current-weather-report";
import { RainfallDetailPanel } from "@/components/rainfall-detail-panel";
import { SunPathPanel } from "@/components/sun-path-panel";
import { TemperatureDetailPanel } from "@/components/temperature-detail-panel";
import { WarningsDetailPanel } from "@/components/warnings-detail-panel";
import type { WeatherDetailSection } from "@/components/weather-detail-sections";
import { WeatherWarnings } from "@/components/weather-warnings";
import {
  INITIAL_WEATHER_STALE_AFTER,
  type InitialWeatherState,
} from "@/lib/weather/initial";
import { currentWeatherViewModel } from "@/lib/weather/view-models";
import { useSettings } from "@/lib/weather/settings";
import { weatherClient } from "@/lib/weather/client";
import type { WeatherSectionState } from "@/lib/weather/state";
import { loadedWeatherSection } from "@/lib/weather/state";
import {
  activeWarnings,
  warningDisplayName,
  warningSummaryHeadline,
} from "@/lib/weather";
import type {
  Warnings,
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

const DASHBOARD_REFRESH_INTERVAL_MS = 10 * 60_000;
const DASHBOARD_FOCUS_REFRESH_AFTER_MS = 5 * 60_000;

export function WeatherDashboard({
  initialWeather,
  initialNow,
}: {
  initialWeather: InitialWeatherState;
  initialNow: string;
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

  const { settings, setAvailableStations, setAvailableDistricts } = useSettings();

  const tempDist = settings.temperatureDistrict === "__default__"
    ? undefined
    : settings.temperatureDistrict;
  const rainDist = settings.rainfallDistrict === "__default__"
    ? undefined
    : settings.rainfallDistrict;

  useEffect(() => {
    if (currentSection) {
      const stations = currentSection.data.temperature?.data.map((t) => t.place) ?? [];
      setAvailableStations(stations);
      const districts = currentSection.data.rainfall?.data.map((r) => r.place) ?? [];
      setAvailableDistricts(districts);
    }
  }, [currentSection, setAvailableStations, setAvailableDistricts]);

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
    let stopped = false;
    let inFlight = false;
    let lastRefreshAt = Date.now();

    async function refreshDashboard(force: boolean) {
      if (
        stopped ||
        inFlight ||
        document.visibilityState !== "visible" ||
        (!force &&
          Date.now() - lastRefreshAt < DASHBOARD_FOCUS_REFRESH_AFTER_MS)
      ) {
        return;
      }

      inFlight = true;
      try {
        const { data } = await weatherClient.getDashboard();
        if (stopped) return;
        const now = new Date();
        if (data.current) {
          setCurrentSection(
            loadedWeatherSection(
              data.current,
              INITIAL_WEATHER_STALE_AFTER.current,
              now,
            ),
          );
        }
        if (data.warnings) {
          setWarningsSection(
            loadedWeatherSection(
              data.warnings,
              INITIAL_WEATHER_STALE_AFTER.warnings,
              now,
            ),
          );
        }
        if (data.regionalTemperature) {
          setRegionalTemperature(
            loadedWeatherSection(
              data.regionalTemperature,
              INITIAL_WEATHER_STALE_AFTER.regionalTemperature,
              now,
            ),
          );
        }
        if (data.regionalWind) {
          setRegionalWind(
            loadedWeatherSection(
              data.regionalWind,
              INITIAL_WEATHER_STALE_AFTER.regionalWind,
              now,
            ),
          );
        }
        if (data.lampposts) {
          setLampposts(
            loadedWeatherSection(
              data.lampposts,
              INITIAL_WEATHER_STALE_AFTER.lampposts,
              now,
            ),
          );
        }
        if (data.stationRainfall) {
          setStationRainfall(
            loadedWeatherSection(
              data.stationRainfall,
              INITIAL_WEATHER_STALE_AFTER.stationRainfall,
              now,
            ),
          );
        }
        if (data.localForecast) {
          setLocalForecast(
            loadedWeatherSection(
              data.localForecast,
              INITIAL_WEATHER_STALE_AFTER.localForecast,
              now,
            ),
          );
        }
        lastRefreshAt = Date.now();
      } catch {
        // Keep displaying the last successful snapshot until the next refresh.
      } finally {
        inFlight = false;
      }
    }

    function refreshIfDue() {
      void refreshDashboard(false);
    }

    const interval = window.setInterval(
      () => void refreshDashboard(true),
      DASHBOARD_REFRESH_INTERVAL_MS,
    );
    window.addEventListener("focus", refreshIfDue);
    document.addEventListener("visibilitychange", refreshIfDue);
    return () => {
      stopped = true;
      window.clearInterval(interval);
      window.removeEventListener("focus", refreshIfDue);
      document.removeEventListener("visibilitychange", refreshIfDue);
    };
  }, []);

  const vm = currentSection
    ? currentWeatherViewModel(currentSection.data, tempDist, rainDist)
    : null;
  const currentUpdatedAt = currentSection
    ? currentSection.fetchedAt
    : null;

  const warningsUpdatedAt = warningsSection
    ? (warningsSection.sourceUpdatedAt ?? warningsSection.fetchedAt)
    : null;
  const astronomicalSection = initialWeather.astronomical.status === "ready" ||
    initialWeather.astronomical.status === "stale"
    ? initialWeather.astronomical
    : null;
  const astronomical = astronomicalSection?.data ?? null;

  return (
    <main
      className="weather-page weather-dashboard"
      data-active-section={activeSection ?? undefined}
    >
      <div className="weather-left-column">
        <CurrentWeatherReport
          temperature={vm?.temperature ?? null}
          temperatureDistrict={vm?.temperatureDistrict ?? null}
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
                  stationRainfall={stationRainfall ?? initialWeather.stationRainfall}
                  localForecast={localForecast ?? initialWeather.localForecast}
                />
              ) : activeDetail.id === "warnings" && warningsData ? (
                <WarningsDetailPanel warnings={warningsData} />
              ) : activeDetail.id === "uv" ? (
                <SunPathPanel
                  astronomical={astronomical}
                  initialNow={initialNow}
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
