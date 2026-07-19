import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import type { WeatherFetch } from "./client.ts";

export function readWeatherFixture(name: string): unknown {
  const fixturePath = resolve(
    process.cwd(),
    "fixtures",
    "weather",
    `${name}.json`,
  );
  return JSON.parse(readFileSync(fixturePath, "utf8")) as unknown;
}

export function fixtureFetch(
  routes: Record<string, string | { fixture?: string; status: number; body?: unknown }>,
): WeatherFetch {
  return async (input) => {
    const url = input.toString();
    const path = url.startsWith("http") ? new URL(url).pathname : url;
    const route = routes[path];
    if (route === undefined) {
      return Response.json({ detail: "Unexpected fixture route" }, { status: 404 });
    }
    if (typeof route === "string") {
      return Response.json(readWeatherFixture(route));
    }
    const body = route.fixture
      ? readWeatherFixture(route.fixture)
      : route.body ?? { detail: "Weather data unavailable" };
    return Response.json(body, { status: route.status });
  };
}
