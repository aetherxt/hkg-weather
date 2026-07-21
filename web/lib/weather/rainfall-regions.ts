import type { TemperatureRegionId } from "@/lib/weather/temperature-regions";

export interface RainfallStationItem {
  id: string;
  label: string;
  regionId: TemperatureRegionId;
  value: number | null;
}

export const rainfallDefaultRegionOrder: TemperatureRegionId[] = [
  "hong-kong-island",
  "kowloon",
  "new-territories-east",
  "new-territories-west",
  "outlying-islands",
];

const stationsByRegion: Record<TemperatureRegionId, readonly string[]> = {
  "hong-kong-island": [
    "Shau Kei Wan",
    "Happy Valley",
    "The Peak",
    "Magazine Gap",
    "Stanley",
    "Wong Chuk Hang",
  ],
  kowloon: [
    "Broadcast Drive",
    "Sham Shui Po",
    "Hong Kong Observatory",
    "King\u2019s Park",
    "Kai Tak",
    "San Po Kong",
    "Kwun Tong",
  ],
  "new-territories-east": [
    "Tai Mei Tuk",
    "Tai Po Market",
    "Pak Tam Chung",
    "Kau Sai Chau",
    "Sai Kung",
    "Tseung Kwan O",
    "Clear Water Bay",
    "Sha Tin",
  ],
  "new-territories-west": [
    "Lau Fau Shan",
    "Wetland Park",
    "Shui Pin Wai",
    "Shek Kong",
    "Ta Kwu Ling",
    "Sheung Shui",
    "Tai Lung",
    "Tsuen Wan Ho Koon",
    "Tuen Mun",
    "Cheung Ching",
  ],
  "outlying-islands": [
    "Waglan Island",
    "Cheung Chau",
    "Peng Chau",
    "Ngong Ping",
    "Hong Kong International Airport",
  ],
};

const rainfallDisplayNames: Record<string, string> = {
  "Hong Kong Observatory": "HK Observatory",
  "Hong Kong International Airport": "Chek Lap Kok",
};

export function rainfallStationLabel(station: string): string {
  return rainfallDisplayNames[station] ?? station;
}

const stationRegionLookup = Object.fromEntries(
  Object.entries(stationsByRegion).flatMap(([regionId, stations]) =>
    stations.map((station) => [station, regionId as TemperatureRegionId]),
  ),
) as Record<string, TemperatureRegionId>;

export function rainfallStationRegion(station: string): TemperatureRegionId {
  return stationRegionLookup[station] ?? "new-territories-west";
}

export function rainfallStationId(stationId: string): string {
  return `rainfall:${stationId}`;
}

export function buildRainfallStationItems(
  readings: { automaticWeatherStation: string; automaticWeatherStationID: string; value: number | null }[],
): RainfallStationItem[] {
  return readings.map((r) => ({
    id: rainfallStationId(r.automaticWeatherStationID),
    label: rainfallStationLabel(r.automaticWeatherStation),
    regionId: rainfallStationRegion(r.automaticWeatherStation),
    value: r.value,
  }));
}

export function normalizeRainfallRegionOrder(
  regionOrder: readonly string[] | null | undefined,
): TemperatureRegionId[] {
  const seen = new Set<TemperatureRegionId>();
  const normalized: TemperatureRegionId[] = [];

  for (const regionId of regionOrder ?? []) {
    if (!rainfallDefaultRegionOrder.includes(regionId as TemperatureRegionId)) continue;
    if (seen.has(regionId as TemperatureRegionId)) continue;
    seen.add(regionId as TemperatureRegionId);
    normalized.push(regionId as TemperatureRegionId);
  }

  for (const regionId of rainfallDefaultRegionOrder) {
    if (seen.has(regionId)) continue;
    normalized.push(regionId);
  }

  return normalized;
}

export function groupRainfallStations(
  items: RainfallStationItem[],
  regionOrder: readonly TemperatureRegionId[],
) {
  return regionOrder
    .map((regionId) => {
      const region = { id: regionId, label: regionLabel(regionId) };
      const filtered = items.filter((item) => item.regionId === regionId);
      if (filtered.length === 0) return null;
      return { id: region.id, label: region.label, items: filtered };
    })
    .filter((g): g is { id: TemperatureRegionId; label: string; items: RainfallStationItem[] } => g !== null);
}

function regionLabel(id: TemperatureRegionId): string {
  const labels: Record<TemperatureRegionId, string> = {
    "hong-kong-island": "Hong Kong Island",
    kowloon: "Kowloon",
    "new-territories-east": "New Territories East",
    "new-territories-west": "New Territories West",
    "outlying-islands": "Outlying Islands",
  };
  return labels[id];
}
