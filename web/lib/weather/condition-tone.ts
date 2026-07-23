export type WeatherConditionTone = "rain" | "cloudy" | "sunny" | "neutral";

export function getConditionTone(condition: string): WeatherConditionTone {
  const normalizedCondition = condition.toLowerCase();

  if (
    normalizedCondition.includes("shower") ||
    normalizedCondition.includes("rain") ||
    normalizedCondition.includes("drizzle") ||
    normalizedCondition.includes("thunder")
  ) {
    return "rain";
  }

  if (
    normalizedCondition.includes("cloud") ||
    normalizedCondition.includes("overcast")
  ) {
    return "cloudy";
  }

  if (
    normalizedCondition.includes("sun") ||
    normalizedCondition.includes("fine") ||
    normalizedCondition.includes("clear")
  ) {
    return "sunny";
  }

  return "neutral";
}
