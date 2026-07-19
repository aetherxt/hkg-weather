const ICON_DESCRIPTIONS: Record<number, string> = {
  50: "Sunny",
  51: "Sunny Periods",
  52: "Sunny Intervals",
  53: "Sunny Periods with A Few Showers",
  54: "Sunny Intervals with Showers",
  60: "Cloudy",
  61: "Overcast",
  62: "Light Rain",
  63: "Rain",
  64: "Heavy Rain",
  65: "Thunderstorms",
  70: "Fine",
  71: "Fine",
  72: "Fine",
  73: "Fine",
  74: "Fine",
  75: "Fine",
  76: "Mainly Cloudy",
  77: "Mainly Fine",
  80: "Windy",
  81: "Dry",
  82: "Humid",
  83: "Fog",
  84: "Mist",
  85: "Haze",
  90: "Hot",
  91: "Warm",
  92: "Cool",
  93: "Cold",
};

export function iconDescription(icon: number): string | undefined {
  return ICON_DESCRIPTIONS[icon];
}

export function primaryIconDescription(icons: number[]): string | undefined {
  for (const code of icons) {
    const description = iconDescription(code);
    if (description) return description;
  }
  return undefined;
}
