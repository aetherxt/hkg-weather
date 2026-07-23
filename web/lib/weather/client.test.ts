import assert from "node:assert/strict";
import test from "node:test";

import {
  createWeatherClient,
  WeatherApiError,
  WeatherResponseDecodeError,
  type WeatherApiErrorKind,
  type WeatherApiErrorStatus,
  type WeatherFetch,
} from "./client.ts";
import { fixtureFetch, readWeatherFixture } from "./test-helpers.ts";

test("the same-origin client decodes a typed data response", async () => {
  let requestedUrl: string | null = null;
  let requestedInit: RequestInit | undefined;
  const fetch: WeatherFetch = async (input, init) => {
    requestedUrl = input.toString();
    requestedInit = init;
    return Response.json(readWeatherFixture("current"));
  };
  const client = createWeatherClient({ fetch });

  const response = await client.getCurrentWeather();

  assert.equal(requestedUrl, "/api/weather/current");
  assert.equal(requestedInit?.method, "GET");
  assert.equal(new Headers(requestedInit?.headers).get("accept"), "application/json");
  assert.equal(response.data.temperature?.data[0]?.place, "King's Park");
  assert.equal(response.meta.dataset, "current_weather");
});

test("the dashboard client uses one aggregate endpoint", async () => {
  let requestedUrl = "";
  const client = createWeatherClient({
    fetch: async (input) => {
      requestedUrl = input.toString();
      return Response.json({
        data: {
          warnings: null,
          current: readWeatherFixture("current"),
          localForecast: null,
          nineDayForecast: null,
          regionalTemperature: null,
          regionalWind: null,
          lampposts: null,
          astronomical: null,
          stationRainfall: null,
        },
        meta: {
          dataset: "dashboard",
          sourceUpdatedAt: "2026-07-18T10:00:00Z",
          fetchedAt: "2026-07-18T10:01:00Z",
        },
      });
    },
  });

  const response = await client.getDashboard();

  assert.equal(requestedUrl, "/api/weather/dashboard");
  assert.equal(response.data.current?.data.icon[0], 62);
});

test("the server client resolves weather paths against its application origin", async () => {
  let requestedUrl = "";
  const fetch: WeatherFetch = async (input) => {
    requestedUrl = input.toString();
    return Response.json(readWeatherFixture("local-forecast"));
  };
  const client = createWeatherClient({
    baseUrl: "https://weather.example/ignored/path",
    fetch,
  });

  await client.getLocalForecast();

  assert.equal(
    requestedUrl,
    "https://weather.example/api/weather/forecast/local",
  );
});

test("list readers require and preserve list metadata", async () => {
  const client = createWeatherClient({
    fetch: fixtureFetch({
      "/api/weather/regional/temperature": "regional-temperature",
    }),
  });

  const response = await client.getRegionalTemperature();

  assert.equal(response.data.length, 2);
  assert.equal(response.data[0]?.temperatureC, 30.9);
  assert.equal(response.meta.count, 2);
});

test("tropical cyclone reader uses the active cyclone endpoint", async () => {
  let requestedUrl = "";
  const client = createWeatherClient({
    fetch: async (input) => {
      requestedUrl = input.toString();
      return Response.json({
        data: [
          {
            stormId: "2601",
            nameEn: "ALPHA",
            nameZh: "阿爾法",
            fetchedAt: "2026-07-23T06:01:00Z",
            geoJson: { type: "FeatureCollection", features: [] },
            potentialTrackAreaGeoJson: {
              type: "FeatureCollection",
              features: [],
            },
          },
        ],
        meta: {
          dataset: "tropical_cyclone_track",
          sourceUpdatedAt: "2026-07-23T06:00:00Z",
          fetchedAt: "2026-07-23T06:01:00Z",
          count: 1,
        },
      });
    },
  });

  const response = await client.getTropicalCyclones();

  assert.equal(requestedUrl, "/api/weather/tropical-cyclones");
  assert.equal(response.data[0]?.nameEn, "ALPHA");
  assert.equal(response.meta.count, 1);
});

test("tropical cyclone history reader bounds the requested archive range", async () => {
  let requestedUrl = "";
  const client = createWeatherClient({
    fetch: async (input) => {
      requestedUrl = input.toString();
      return Response.json({
        data: [],
        meta: {
          dataset: "tropical_cyclone_track:2601",
          sourceUpdatedAt: null,
          fetchedAt: null,
          count: 0,
        },
      });
    },
  });

  await client.getTropicalCycloneHistory(
    "2601",
    "2026-07-20T06:00:00.000Z",
    "2026-07-23T06:00:00.000Z",
  );

  assert.equal(
    requestedUrl,
    "/api/weather/history/tropical-cyclones/2601" +
      "?from=2026-07-20T06%3A00%3A00.000Z&to=2026-07-23T06%3A00%3A00.000Z",
  );
});

test("lamppost list reader returns structured device readings", async () => {
  const client = createWeatherClient({
    fetch: fixtureFetch({
      "/api/weather/lampposts": "lampposts",
    }),
  });

  const response = await client.getLampposts();

  assert.equal(response.data.length, 4);
  assert.equal(response.data[0]?.label, "Central");
  assert.equal(response.meta.count, 4);
});

const errorCases: Array<{
  status: WeatherApiErrorStatus;
  kind: WeatherApiErrorKind;
  body: unknown;
}> = [
  {
    status: 404,
    kind: "not-found",
    body: { detail: "Weather data not found" },
  },
  {
    status: 422,
    kind: "invalid-request",
    body: {
      detail: [
        {
          type: "value_error",
          loc: ["path", "stationCode"],
          msg: "Unsupported station",
        },
      ],
    },
  },
  {
    status: 503,
    kind: "unavailable",
    body: { detail: "Weather data unavailable" },
  },
];

for (const { status, kind, body } of errorCases) {
  test(`status ${status} becomes the ${kind} API error`, async () => {
    const client = createWeatherClient({
      fetch: fixtureFetch({
        "/api/weather/current": { status, body },
      }),
    });

    await assert.rejects(client.getCurrentWeather(), (error: unknown) => {
      assert.ok(error instanceof WeatherApiError);
      assert.equal(error.status, status);
      assert.equal(error.kind, kind);
      assert.equal(error.endpoint, "/api/weather/current");
      return true;
    });
  });
}

test("malformed JSON never crosses the data boundary", async () => {
  const client = createWeatherClient({
    fetch: async () => new Response("not json", { status: 200 }),
  });

  await assert.rejects(
    client.getWarnings(),
    (error: unknown) => error instanceof WeatherResponseDecodeError,
  );
});

test("successful responses require normalized metadata", async () => {
  const client = createWeatherClient({
    fetch: async () => Response.json({ data: {}, meta: { dataset: "warnings" } }),
  });

  await assert.rejects(
    client.getWarnings(),
    (error: unknown) => error instanceof WeatherResponseDecodeError,
  );
});
