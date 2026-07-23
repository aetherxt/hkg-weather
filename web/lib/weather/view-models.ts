import { primaryIconDescription } from "./icon-map.ts";
import type { CurrentWeather } from "./types.ts";

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
  const temperatures = Array.isArray(data.temperature?.data)
    ? data.temperature.data
    : [];
  const humidities = Array.isArray(data.humidity?.data)
    ? data.humidity.data
    : [];
  const rainfallReadings = Array.isArray(data.rainfall?.data)
    ? data.rainfall.data
    : [];
  const uvReadings = Array.isArray(data.uvindex?.data)
    ? data.uvindex.data
    : [];
  const temp = temperatureDistrict
    ? temperatures.find((t) => t.place === temperatureDistrict)
    : undefined;
  const hkoTemp = temperatures.find(
    (t) => t.place === HKO_STATION,
  );
  const hkoHumidity = humidities.find(
    (h) => h.place === HKO_STATION,
  );
  const rain = rainfallDistrict
    ? rainfallReadings.find((r) => r.place === rainfallDistrict)
    : undefined;
  const mainRainfall = rainfallReadings.find(
    (r) => r.main === "TRUE",
  );
  const firstRainfall = rainfallReadings[0];
  const uv = uvReadings[0];

  const resolvedDistrict =
    temp?.place ?? hkoTemp?.place ?? temperatures[0]?.place ?? null;

  return {
    temperature: temp?.value ?? hkoTemp?.value ?? temperatures[0]?.value ?? null,
    temperatureDistrict: resolvedDistrict ? temperatureDisplayName(resolvedDistrict) : null,
    condition: primaryIconDescription(
      Array.isArray(data.icon) ? data.icon : [],
    ) ?? null,
    humidity: hkoHumidity?.value ?? humidities[0]?.value ?? null,
    rainfall: rain?.max ?? mainRainfall?.max ?? firstRainfall?.max ?? null,
    uvIndex: uv?.value ?? null,
    uvLevel: uv?.desc ? uv.desc.charAt(0).toUpperCase() + uv.desc.slice(1) : null,
  };
}
