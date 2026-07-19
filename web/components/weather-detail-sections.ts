export const weatherDetailSections = [
  "temperature",
  "rainfall-wind",
  "warnings",
  "uv",
] as const;

export type WeatherDetailSection = (typeof weatherDetailSections)[number];

export interface WeatherDetailInteractionProps {
  activeSection: WeatherDetailSection | null;
  onSelectSection: (section: WeatherDetailSection) => void;
}
