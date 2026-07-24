import { getMoonIllumination } from "suncalc";

export interface MoonData {
  phase: string;
  illumination: number;
  emoji: string;
}

const MOON_PHASES = [
  { min: 0, max: 0.0625, name: "New Moon", emoji: "\uD83C\uDF11" },
  { min: 0.0625, max: 0.1875, name: "Waxing Crescent", emoji: "\uD83C\uDF12" },
  { min: 0.1875, max: 0.3125, name: "First Quarter", emoji: "\uD83C\uDF13" },
  { min: 0.3125, max: 0.4375, name: "Waxing Gibbous", emoji: "\uD83C\uDF14" },
  { min: 0.4375, max: 0.5625, name: "Full Moon", emoji: "\uD83C\uDF15" },
  { min: 0.5625, max: 0.6875, name: "Waning Gibbous", emoji: "\uD83C\uDF16" },
  { min: 0.6875, max: 0.8125, name: "Last Quarter", emoji: "\uD83C\uDF17" },
  { min: 0.8125, max: 1, name: "Waning Crescent", emoji: "\uD83C\uDF18" },
] as const;

export function getMoonData(date: Date): MoonData {
  const { phase, fraction } = getMoonIllumination(date);
  const entry =
    MOON_PHASES.find((p) => phase >= p.min && phase < p.max) ?? MOON_PHASES[0];
  return {
    phase: entry.name,
    illumination: Math.round(fraction * 100),
    emoji: entry.emoji,
  };
}
