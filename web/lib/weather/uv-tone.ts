export type UvTone =
  | "low"
  | "moderate"
  | "high"
  | "very-high"
  | "extreme";

export function getUvTone(uvIndex: number): UvTone {
  if (uvIndex <= 2) return "low";
  if (uvIndex <= 5) return "moderate";
  if (uvIndex <= 7) return "high";
  if (uvIndex <= 10) return "very-high";
  return "extreme";
}
