export const SETTINGS_COOKIE_NAME = "hkw-settings";

export type ThemeMode = "system" | "light" | "dark";

export interface UserSettings {
  temperatureDistrict: string;
  rainfallDistrict: string;
  themeMode: ThemeMode;
}

export const DEFAULT_SETTINGS: Readonly<UserSettings> = {
  temperatureDistrict: "__default__",
  rainfallDistrict: "__default__",
  themeMode: "system",
};

function cookieString(value: unknown, fallback: string): string {
  return typeof value === "string" && value.length > 0 ? value : fallback;
}

function cookieTheme(value: unknown): ThemeMode {
  return value === "light" || value === "dark" || value === "system"
    ? value
    : DEFAULT_SETTINGS.themeMode;
}

export function parseSettingsCookie(raw: string | null | undefined): UserSettings {
  if (!raw) return { ...DEFAULT_SETTINGS };

  try {
    const parsed = JSON.parse(decodeURIComponent(raw)) as Record<string, unknown>;

    return {
      temperatureDistrict: cookieString(
        parsed.temperatureDistrict,
        DEFAULT_SETTINGS.temperatureDistrict,
      ),
      rainfallDistrict: cookieString(
        parsed.rainfallDistrict,
        DEFAULT_SETTINGS.rainfallDistrict,
      ),
      themeMode: cookieTheme(parsed.themeMode),
    };
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}
