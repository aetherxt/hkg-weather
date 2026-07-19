import { regionalStationLocations } from "@/lib/weather/station-locations";
import type { LamppostReading, TemperatureReading } from "@/lib/weather/types";

export type TemperatureRegionId =
  | "hong-kong-island"
  | "kowloon"
  | "new-territories-east"
  | "new-territories-west"
  | "outlying-islands";

export interface TemperatureRegion {
  id: TemperatureRegionId;
  label: string;
}

export interface TemperatureSensorItem {
  id: string;
  kind: "station" | "lamppost";
  label: string;
  regionId: TemperatureRegionId;
  temperature: string | null;
  humidity: string | null;
}

export const temperatureRegions: readonly TemperatureRegion[] = [
  { id: "hong-kong-island", label: "Hong Kong Island" },
  { id: "kowloon", label: "Kowloon" },
  { id: "new-territories-east", label: "New Territories East" },
  { id: "new-territories-west", label: "New Territories West" },
  { id: "outlying-islands", label: "Outlying Islands" },
];

export const defaultTemperatureRegionOrder = temperatureRegions.map((region) => region.id);

const stationsByRegion: Readonly<Record<TemperatureRegionId, readonly string[]>> = {
  "hong-kong-island": [
    "Happy Valley",
    "HK Park",
    "Shau Kei Wan",
    "Stanley",
    "The Peak",
    "Wong Chuk Hang",
  ],
  kowloon: [
    "HK Observatory",
    "Kai Tak Runway Park",
    "King's Park",
    "Kowloon City",
    "Kwun Tong",
    "Sham Shui Po",
    "Wong Tai Sin",
  ],
  "new-territories-east": [
    "Clear Water Bay",
    "Pak Tam Chung",
    "Sai Kung",
    "Sha Tin",
    "Tai Lung",
    "Tai Mei Tuk",
    "Tai Po",
    "Tate's Cairn",
    "Tseung Kwan O",
  ],
  "new-territories-west": [
    "Lau Fau Shan",
    "Shek Kong",
    "Sheung Shui",
    "Ta Kwu Ling",
    "Tai Mo Shan",
    "Tsing Yi",
    "Tsuen Wan Ho Koon",
    "Tsuen Wan Shing Mun Valley",
    "Tuen Mun",
    "Wetland Park",
    "Yuen Long Park",
  ],
  "outlying-islands": [
    "Chek Lap Kok",
    "Cheung Chau",
    "Kau Sai Chau",
    "Ngong Ping",
    "Peng Chau",
    "Waglan Island",
  ],
};

const stationRegionLookup = Object.fromEntries(
  Object.entries(stationsByRegion).flatMap(([regionId, stations]) =>
    stations.map((station) => [station, regionId as TemperatureRegionId]),
  ),
) as Record<string, TemperatureRegionId>;

const lamppostRegionLookup: Record<string, TemperatureRegionId> = {
  Central: "hong-kong-island",
  "Wan Chai": "hong-kong-island",
  "Tsim Sha Tsui / Jordan": "kowloon",
  "Kowloon Bay / Choi Hung": "kowloon",
};

function readingTemperature(reading: Record<string, unknown>) {
  const body = reading.body;
  const hko = body && typeof body === "object" && "hko" in body
    ? (body as Record<string, unknown>).hko
    : null;
  if (!hko || typeof hko !== "object") return null;
  const temperature = (hko as Record<string, unknown>).t0;
  return temperature == null ? null : String(temperature);
}

function readingHumidity(reading: Record<string, unknown>) {
  const body = reading.body;
  const hko = body && typeof body === "object" && "hko" in body
    ? (body as Record<string, unknown>).hko
    : null;
  if (!hko || typeof hko !== "object") return null;
  const humidity = (hko as Record<string, unknown>).rh;
  return humidity == null ? null : String(humidity);
}

function fallbackRegion(longitude: number, latitude: number): TemperatureRegionId {
  if (latitude < 22.245 || longitude < 114.05) return "outlying-islands";
  if (latitude < 22.29) return "hong-kong-island";
  if (latitude < 22.35) return "kowloon";
  if (longitude >= 114.2 || latitude >= 22.39) return "new-territories-east";
  return "new-territories-west";
}

export function stationSensorId(station: string) {
  return `station:${station}`;
}

export function lamppostSensorId(lamppost: Pick<LamppostReading, "lamppostId" | "deviceId">) {
  return `lamppost:${lamppost.lamppostId}:${lamppost.deviceId}`;
}

export function normalizeTemperatureRegionOrder(regionOrder: readonly string[] | null | undefined) {
  const seen = new Set<TemperatureRegionId>();
  const normalized: TemperatureRegionId[] = [];

  for (const regionId of regionOrder ?? []) {
    if (!defaultTemperatureRegionOrder.includes(regionId as TemperatureRegionId)) continue;
    if (seen.has(regionId as TemperatureRegionId)) continue;
    seen.add(regionId as TemperatureRegionId);
    normalized.push(regionId as TemperatureRegionId);
  }

  for (const regionId of defaultTemperatureRegionOrder) {
    if (seen.has(regionId)) continue;
    normalized.push(regionId);
  }

  return normalized;
}

export function buildTemperatureSensorItems({
  regionalReadings,
  lamppostReadings,
  includeAllStations = false,
}: {
  regionalReadings: TemperatureReading[];
  lamppostReadings: LamppostReading[];
  includeAllStations?: boolean;
}) {
  const stationReadings = new Map(
    regionalReadings.map((reading) => [reading.station, reading]),
  );
  const stationNames = includeAllStations
    ? Object.keys(regionalStationLocations)
    : regionalReadings.map((reading) => reading.station);

  const stations: TemperatureSensorItem[] = stationNames
    .filter((station, index, array) => array.indexOf(station) === index)
    .map((station) => {
      const reading = stationReadings.get(station) ?? null;
      return {
        id: stationSensorId(station),
        kind: "station",
        label: station,
        regionId: stationRegionLookup[station] ?? "new-territories-west",
        temperature: reading?.temperatureC == null ? null : String(reading.temperatureC),
        humidity: null,
      };
    });

  const lampposts: TemperatureSensorItem[] = lamppostReadings.map((lamppost) => ({
    id: lamppostSensorId(lamppost),
    kind: "lamppost",
    label: lamppost.label,
    regionId:
      lamppostRegionLookup[lamppost.label] ??
      fallbackRegion(lamppost.longitude, lamppost.latitude),
    temperature: readingTemperature(lamppost.reading),
    humidity: readingHumidity(lamppost.reading),
  }));

  return [...stations, ...lampposts].sort((left, right) => {
    if (left.regionId !== right.regionId) {
      return defaultTemperatureRegionOrder.indexOf(left.regionId) -
        defaultTemperatureRegionOrder.indexOf(right.regionId);
    }
    if (left.kind !== right.kind) {
      return left.kind === "station" ? -1 : 1;
    }
    return left.label.localeCompare(right.label, "en");
  });
}

export function groupTemperatureSensors(
  sensors: TemperatureSensorItem[],
  regionOrder: readonly TemperatureRegionId[],
) {
  return regionOrder
    .map((regionId) => {
      const region = temperatureRegions.find((item) => item.id === regionId);
      const items = sensors.filter((sensor) => sensor.regionId === regionId);
      if (!region || items.length === 0) return null;
      return {
        id: region.id,
        label: region.label,
        items,
      };
    })
    .filter((group): group is { id: TemperatureRegionId; label: string; items: TemperatureSensorItem[] } => group !== null);
}
