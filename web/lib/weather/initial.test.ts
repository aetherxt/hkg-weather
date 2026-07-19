import assert from "node:assert/strict";
import test from "node:test";

import { createWeatherClient } from "./client.ts";
import { loadInitialWeather } from "./initial.ts";
import {
  loadingWeatherSection,
  retryingWeatherSection,
} from "./state.ts";
import { fixtureFetch } from "./test-helpers.ts";

const successRoutes = {
  "/api/weather/warnings": "warnings",
  "/api/weather/current": "current",
  "/api/weather/forecast/local": "local-forecast",
  "/api/weather/forecast/nine-day": "nine-day-forecast",
  "/api/weather/regional/temperature": "regional-temperature",
  "/api/weather/regional/wind": "regional-wind",
  "/api/weather/lampposts": "lampposts",
  "/api/weather/sun": "astronomical",
  "/api/weather/rainfall/stations": "station-rainfall",
} as const;

test("initial page data loads every non-map section from fixtures", async () => {
  const client = createWeatherClient({ fetch: fixtureFetch(successRoutes) });

  const state = await loadInitialWeather(
    client,
    new Date("2026-07-18T10:10:00Z"),
  );

  assert.equal(state.warnings.status, "stale");
  assert.equal(state.current.status, "ready");
  assert.equal(state.localForecast.status, "ready");
  assert.equal(state.nineDayForecast.status, "ready");
  assert.equal(state.regionalTemperature.status, "ready");
  assert.equal(state.regionalWind.status, "ready");
  assert.equal(state.lampposts.status, "ready");
  assert.equal(state.astronomical.status, "ready");
  assert.equal(state.stationRainfall.status, "ready");

  if (state.warnings.status === "stale") {
    assert.equal(state.warnings.sourceUpdatedAt, "2026-07-18T09:10:00Z");
    assert.equal(state.warnings.fetchedAt, "2026-07-18T10:00:17.975000Z");
    assert.notEqual(state.warnings.sourceUpdatedAt, state.warnings.fetchedAt);
  }
  if (state.nineDayForecast.status === "ready") {
    assert.equal(state.nineDayForecast.data.weatherForecast.length, 2);
  }
});

test("one unavailable feed does not fail the other initial sections", async () => {
  const client = createWeatherClient({
    fetch: fixtureFetch({
      ...successRoutes,
      "/api/weather/current": {
        status: 503,
        body: { detail: "Weather storage unavailable" },
      },
    }),
  });

  const state = await loadInitialWeather(
    client,
    new Date("2026-07-18T10:10:00Z"),
  );

  assert.equal(state.current.status, "unavailable");
  if (state.current.status === "unavailable") {
    assert.equal(state.current.error.kind, "unavailable");
    assert.equal(state.current.error.status, 503);
    assert.equal(state.current.canRetry, true);
  }
  assert.notEqual(state.localForecast.status, "unavailable");
  assert.notEqual(state.regionalTemperature.status, "unavailable");
});

test("loading and retrying states share the section-state vocabulary", () => {
  assert.deepEqual(loadingWeatherSection(), { status: "loading" });
  assert.deepEqual(retryingWeatherSection(), { status: "retrying" });
});
