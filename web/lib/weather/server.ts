import { headers } from "next/headers";

import { createWeatherClient } from "./client.ts";
import {
  loadInitialWeather,
  type InitialWeatherState,
} from "./initial.ts";

function firstForwardedValue(value: string | null): string | null {
  return value?.split(",", 1)[0]?.trim() || null;
}

async function requestOrigin(): Promise<string> {
  const requestHeaders = await headers();
  const host =
    firstForwardedValue(requestHeaders.get("x-forwarded-host")) ??
    requestHeaders.get("host");
  if (!host) {
    throw new Error("Cannot resolve the application origin for weather data");
  }
  const forwardedProtocol = firstForwardedValue(
    requestHeaders.get("x-forwarded-proto"),
  );
  const protocol =
    forwardedProtocol ??
    (host.startsWith("localhost") || host.startsWith("127.0.0.1")
      ? "http"
      : "https");
  return new URL(`${protocol}://${host}`).origin;
}

/** Load only the non-interactive data needed for the initial server render. */
export async function loadInitialWeatherForPage(): Promise<InitialWeatherState> {
  const client = createWeatherClient({
    baseUrl: await requestOrigin(),
    requestInit: { cache: "no-store" },
  });
  return loadInitialWeather(client);
}
