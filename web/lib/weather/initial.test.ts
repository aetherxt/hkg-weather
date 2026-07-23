import assert from "node:assert/strict";
import test from "node:test";

import { createWeatherClient } from "./client.ts";
import { loadInitialWeather } from "./initial.ts";
import {
  loadingWeatherSection,
  retryingWeatherSection,
} from "./state.ts";
import { fixtureFetch, readWeatherFixture } from "./test-helpers.ts";

function dashboardResponse(overrides: Record<string, unknown> = {}) {
  return {
    data: {
      warnings: readWeatherFixture("warnings"),
      current: readWeatherFixture("current"),
      localForecast: readWeatherFixture("local-forecast"),
      nineDayForecast: readWeatherFixture("nine-day-forecast"),
      regionalTemperature: readWeatherFixture("regional-temperature"),
      regionalWind: readWeatherFixture("regional-wind"),
      lampposts: readWeatherFixture("lampposts"),
      astronomical: readWeatherFixture("astronomical"),
      stationRainfall: readWeatherFixture("station-rainfall"),
      ...overrides,
    },
    meta: {
      dataset: "dashboard",
      sourceUpdatedAt: "2026-07-18T10:00:00Z",
      fetchedAt: "2026-07-18T10:00:17.975000Z",
    },
  };
}

test("initial page data loads every non-map section from fixtures", async () => {
  let requests = 0;
  const client = createWeatherClient({
    fetch: async (input) => {
      requests += 1;
      assert.equal(input.toString(), "/api/weather/dashboard");
      return Response.json(dashboardResponse());
    },
  });

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
  assert.equal(requests, 1);

  if (state.warnings.status === "stale") {
    assert.equal(state.warnings.sourceUpdatedAt, "2026-07-18T09:10:00Z");
    assert.equal(state.warnings.fetchedAt, "2026-07-18T10:00:17.975000Z");
    assert.notEqual(state.warnings.sourceUpdatedAt, state.warnings.fetchedAt);
  }
  if (state.nineDayForecast.status === "ready") {
    assert.equal(state.nineDayForecast.data.weatherForecast.length, 2);
  }
});

test("one unavailable dashboard section does not fail the others", async () => {
  const client = createWeatherClient({
    fetch: async () => Response.json(dashboardResponse({ current: null })),
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

test("an unavailable dashboard request marks every initial section unavailable", async () => {
  const client = createWeatherClient({
    fetch: fixtureFetch({
      "/api/weather/dashboard": {
        status: 503,
        body: { detail: "Weather storage unavailable" },
      },
    }),
  });

  const state = await loadInitialWeather(client);

  assert.equal(state.current.status, "unavailable");
  assert.equal(state.warnings.status, "unavailable");
  assert.equal(state.astronomical.status, "unavailable");
});

test("loading and retrying states share the section-state vocabulary", () => {
  assert.deepEqual(loadingWeatherSection(), { status: "loading" });
  assert.deepEqual(retryingWeatherSection(), { status: "retrying" });
});
