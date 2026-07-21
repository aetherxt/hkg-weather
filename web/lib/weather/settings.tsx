"use client";

import { createContext, useContext, useState, useCallback, type ReactNode } from "react";

const COOKIE_NAME = "hkw-settings";

export type ThemeMode = "system" | "light" | "dark";

export interface UserSettings {
  temperatureDistrict: string;
  rainfallDistrict: string;
  themeMode: ThemeMode;
}

const DEFAULT_SETTINGS: UserSettings = {
  temperatureDistrict: "__default__",
  rainfallDistrict: "__default__",
  themeMode: "system",
};

function getCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(`(?:^|; )${name}=([^;]*)`);
  return match ? decodeURIComponent(match[1]) : null;
}

function setCookie(name: string, value: string) {
  document.cookie = `${name}=${encodeURIComponent(value)}; path=/; max-age=31536000; SameSite=Lax`;
}

function loadSettings(): UserSettings {
  try {
    const raw = getCookie(COOKIE_NAME);
    if (raw) {
      const parsed = JSON.parse(raw);
      return { ...DEFAULT_SETTINGS, ...parsed };
    }
  } catch {}
  return DEFAULT_SETTINGS;
}

function saveSettings(settings: UserSettings) {
  setCookie(COOKIE_NAME, JSON.stringify(settings));
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

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<UserSettings>(loadSettings);
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
