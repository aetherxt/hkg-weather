import { primaryIconDescription } from "./icon-map";
import type { CurrentWeather } from "./types";

export interface CurrentWeatherViewModel {
  temperature: number | null;
  condition: string | null;
  humidity: number | null;
  rainfall: number | null;
  uvIndex: number | null;
  uvLevel: string | null;
}

const HKO_STATION = "Hong Kong Observatory";

export function currentWeatherViewModel(
  data: CurrentWeather,
): CurrentWeatherViewModel {
  const hkoTemp = data.temperature?.data.find(
    (t) => t.place === HKO_STATION,
  );
  const hkoHumidity = data.humidity?.data.find(
    (h) => h.place === HKO_STATION,
  );
  const mainRainfall = data.rainfall?.data.find(
    (r) => r.main === "TRUE",
  );
  const firstRainfall = data.rainfall?.data[0];
  const uv = data.uvindex?.data[0];

  return {
    temperature: hkoTemp?.value ?? data.temperature?.data[0]?.value ?? null,
    condition: primaryIconDescription(data.icon) ?? null,
    humidity: hkoHumidity?.value ?? data.humidity?.data[0]?.value ?? null,
    rainfall: mainRainfall?.max ?? firstRainfall?.max ?? null,
    uvIndex: uv?.value ?? null,
    uvLevel: uv?.desc ? uv.desc.charAt(0).toUpperCase() + uv.desc.slice(1) : null,
  };
}
