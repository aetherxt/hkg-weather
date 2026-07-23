"use client";

import { createContext, useContext, useState, useCallback, type ReactNode } from "react";
import {
  parseSettingsCookie,
  SETTINGS_COOKIE_NAME,
  type UserSettings,
} from "@/lib/weather/settings-values";

export type { ThemeMode, UserSettings } from "@/lib/weather/settings-values";

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(`(?:^|; )${name}=([^;]*)`);
  return match?.[1] ?? null;
}

function setCookie(name: string, value: string) {
  document.cookie = `${name}=${encodeURIComponent(value)}; path=/; max-age=31536000; SameSite=Lax`;
}

function loadSettings(): UserSettings {
  return parseSettingsCookie(getCookie(SETTINGS_COOKIE_NAME));
}

function saveSettings(settings: UserSettings) {
  setCookie(SETTINGS_COOKIE_NAME, JSON.stringify(settings));
}

interface SettingsContextValue {
  settings: UserSettings;
  updateSettings: (partial: Partial<UserSettings>) => void;
  availableTemperatureStations: string[];
  availableRainfallDistricts: string[];
  setAvailableStations: (stations: string[]) => void;
  setAvailableDistricts: (districts: string[]) => void;
}

const SettingsContext = createContext<SettingsContextValue | null>(null);

export function SettingsProvider({
  children,
  initialSettings,
}: {
  children: ReactNode;
  initialSettings?: UserSettings;
}) {
  const [settings, setSettings] = useState<UserSettings>(() =>
    initialSettings ?? loadSettings(),
  );
  const [availableTemperatureStations, setAvailableTemperatureStations] = useState<string[]>([]);
  const [availableRainfallDistricts, setAvailableRainfallDistricts] = useState<string[]>([]);

  const updateSettings = useCallback((partial: Partial<UserSettings>) => {
    setSettings((prev) => {
      const next = { ...prev, ...partial };
      saveSettings(next);
      return next;
    });
  }, []);

  const setAvailableStations = useCallback((stations: string[]) => {
    setAvailableTemperatureStations(stations);
  }, []);

  const setAvailableDistricts = useCallback((districts: string[]) => {
    setAvailableRainfallDistricts(districts);
  }, []);

  return (
    <SettingsContext.Provider
      value={{
        settings,
        updateSettings,
        availableTemperatureStations,
        availableRainfallDistricts,
        setAvailableStations,
        setAvailableDistricts,
      }}
    >
      {children}
    </SettingsContext.Provider>
  );
}

export function useSettings() {
  const ctx = useContext(SettingsContext);
  if (!ctx) throw new Error("useSettings must be used within SettingsProvider");
  return ctx;
}
