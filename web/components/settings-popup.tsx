"use client";

import { useRef, useLayoutEffect } from "react";
import { useSettings } from "@/lib/weather/settings";

const THEME_OPTIONS = [
  { value: "system" as const, label: "System" },
  { value: "light" as const, label: "Light" },
  { value: "dark" as const, label: "Dark" },
];

export function SettingsPopup({ onClose }: { onClose: () => void }) {
  const {
    settings,
    updateSettings,
    availableTemperatureStations,
    availableRainfallDistricts,
  } = useSettings();

  const themeNavRef = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    const nav = themeNavRef.current;
    if (!nav) return;
    const activeButton = nav.querySelector<HTMLElement>(`[data-theme-active="true"]`);
    if (!activeButton) {
      nav.style.removeProperty("--active-left");
      nav.style.removeProperty("--active-width");
      nav.style.removeProperty("--active-opacity");
      return;
    }
    nav.style.setProperty("--active-left", `${activeButton.offsetLeft}px`);
    nav.style.setProperty("--active-width", `${activeButton.offsetWidth}px`);
    nav.style.setProperty("--active-opacity", "1");
  }, [settings.themeMode]);

  return (
    <>
      <div className="settings-overlay" onClick={onClose} />
      <div className="settings-popup">
        <div className="settings-group">
          <span className="settings-label">Temperature District</span>
          <select
            className="settings-select"
            value={settings.temperatureDistrict}
            onChange={(e) => updateSettings({ temperatureDistrict: e.target.value })}
          >
            <option value="__default__">Default (HKO)</option>
            {availableTemperatureStations.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>

        <div className="settings-group">
          <span className="settings-label">Rainfall District</span>
          <select
            className="settings-select"
            value={settings.rainfallDistrict}
            onChange={(e) => updateSettings({ rainfallDistrict: e.target.value })}
          >
            <option value="__default__">Default (HKO)</option>
            {availableRainfallDistricts.map((d) => (
              <option key={d} value={d}>{d}</option>
            ))}
          </select>
        </div>

        <div className="settings-group">
          <span className="settings-label">Theme</span>
          <div className="settings-theme-nav" ref={themeNavRef}>
            {THEME_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                className="settings-theme-link"
                data-theme-active={settings.themeMode === opt.value ? "true" : undefined}
                onClick={() => updateSettings({ themeMode: opt.value })}
                type="button"
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
