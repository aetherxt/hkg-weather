import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_SETTINGS,
  parseSettingsCookie,
} from "./settings-values.ts";

test("settings cookie restores the selected temperature district", () => {
  const cookie = encodeURIComponent(
    JSON.stringify({
      temperatureDistrict: "King's Park",
      rainfallDistrict: "Yau Tsim Mong",
      themeMode: "dark",
    }),
  );

  assert.deepEqual(parseSettingsCookie(cookie), {
    temperatureDistrict: "King's Park",
    rainfallDistrict: "Yau Tsim Mong",
    themeMode: "dark",
  });
});

test("invalid settings cookies fall back to safe defaults", () => {
  assert.deepEqual(parseSettingsCookie("not-json"), DEFAULT_SETTINGS);
  assert.deepEqual(
    parseSettingsCookie(
      encodeURIComponent(JSON.stringify({ themeMode: "unsupported" })),
    ),
    DEFAULT_SETTINGS,
  );
});
