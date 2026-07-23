import assert from "node:assert/strict";
import test from "node:test";

import type { CurrentWeather } from "./types.ts";
import { currentWeatherViewModel } from "./view-models.ts";

test("current weather view model tolerates observation groups without data arrays", () => {
  const partialWeather = {
    icon: undefined,
    temperature: { recordTime: "2026-07-23T06:00:00Z" },
    humidity: { recordTime: "2026-07-23T06:00:00Z" },
    rainfall: {
      startTime: "2026-07-23T05:00:00Z",
      endTime: "2026-07-23T06:00:00Z",
    },
    uvindex: { recordDesc: "UV index unavailable" },
    updateTime: "2026-07-23T06:00:00Z",
  } as unknown as CurrentWeather;

  assert.deepEqual(currentWeatherViewModel(partialWeather), {
    temperature: null,
    temperatureDistrict: null,
    condition: null,
    humidity: null,
    rainfall: null,
    uvIndex: null,
    uvLevel: null,
  });
});
