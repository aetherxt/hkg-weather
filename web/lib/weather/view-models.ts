import { primaryIconDescription } from "./icon-map";
import type { CurrentWeather } from "./types";

export interface CurrentWeatherViewModel {
  temperature: number | null;
  temperatureDistrict: string | null;
  condition: string | null;
  humidity: number | null;
  rainfall: number | null;
  uvIndex: number | null;
  uvLevel: string | null;
}

const HKO_STATION = "Hong Kong Observatory";

const temperatureDisplayNames: Record<string, string> = {
  "Hong Kong Observatory": "HK Observatory",
  "Tsuen Wan Shing Mun Valley": "Shing Mun Valley",
  "Kai Tak Runway Park": "Kai Tak",
};

export function temperatureDisplayName(name: string): string {
  return temperatureDisplayNames[name] ?? name;
}

export function currentWeatherViewModel(
  data: CurrentWeather,
  temperatureDistrict?: string,
  rainfallDistrict?: string,
): CurrentWeatherViewModel {
  const temp = temperatureDistrict
    ? data.temperature?.data.find((t) => t.place === temperatureDistrict)
    : undefined;
  const hkoTemp = data.temperature?.data.find(
    (t) => t.place === HKO_STATION,
  );
  const hkoHumidity = data.humidity?.data.find(
    (h) => h.place === HKO_STATION,
  );
  const rain = rainfallDistrict
    ? data.rainfall?.data.find((r) => r.place === rainfallDistrict)
    : undefined;
  const mainRainfall = data.rainfall?.data.find(
    (r) => r.main === "TRUE",
  );
  const firstRainfall = data.rainfall?.data[0];
  const uv = data.uvindex?.data[0];

  const resolvedDistrict = temp?.place ?? hkoTemp?.place ?? data.temperature?.data[0]?.place ?? null;

  return {
    temperature: temp?.value ?? hkoTemp?.value ?? data.temperature?.data[0]?.value ?? null,
    temperatureDistrict: resolvedDistrict ? temperatureDisplayName(resolvedDistrict) : null,
    condition: primaryIconDescription(data.icon) ?? null,
    humidity: hkoHumidity?.value ?? data.humidity?.data[0]?.value ?? null,
    rainfall: rain?.max ?? mainRainfall?.max ?? firstRainfall?.max ?? null,
    uvIndex: uv?.value ?? null,
    uvLevel: uv?.desc ? uv.desc.charAt(0).toUpperCase() + uv.desc.slice(1) : null,
  };
}
