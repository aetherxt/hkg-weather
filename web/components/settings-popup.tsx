"use client";

import { useCallback, useRef, useState, useLayoutEffect } from "react";
import { useSettings } from "@/lib/weather/settings";

const THEME_OPTIONS = [
  { value: "system" as const, label: "System" },
  { value: "light" as const, label: "Light" },
  { value: "dark" as const, label: "Dark" },
];

interface DropdownOption {
  value: string;
  label: string;
}

function SettingsDropdown({
  value,
  options,
  defaultOption,
  onChange,
}: {
  value: string;
  options: DropdownOption[];
  defaultOption: DropdownOption;
  onChange: (value: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const selected = options.find((o) => o.value === value) ?? defaultOption;

  const handleSelect = useCallback(
    (v: string) => {
      onChange(v);
      setOpen(false);
    },
    [onChange],
  );

  useLayoutEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  return (
    <div className="settings-dropdown" ref={ref}>
      <button
        className="settings-dropdown-trigger"
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <span>{selected.label}</span>
        <svg className="settings-dropdown-arrow" width="10" height="6" viewBox="0 0 10 6" aria-hidden="true">
          <path d="M1 1l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {open && (
        <ul className="settings-dropdown-list" role="listbox">
          <li
            className={`settings-dropdown-option${defaultOption.value === selected.value ? " settings-dropdown-option-selected" : ""}`}
            role="option"
            aria-selected={defaultOption.value === selected.value}
            onClick={() => handleSelect(defaultOption.value)}
          >
            {defaultOption.label}
          </li>
          {options.map((opt) => (
            <li
              key={opt.value}
              className={`settings-dropdown-option${opt.value === selected.value ? " settings-dropdown-option-selected" : ""}`}
              role="option"
              aria-selected={opt.value === selected.value}
              onClick={() => handleSelect(opt.value)}
            >
              {opt.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

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
          <SettingsDropdown
            value={settings.temperatureDistrict}
            defaultOption={{ value: "__default__", label: "Default (HKO)" }}
            options={availableTemperatureStations.map((s) => ({ value: s, label: s }))}
            onChange={(v) => updateSettings({ temperatureDistrict: v })}
          />
        </div>

        <div className="settings-group">
          <span className="settings-label">Rainfall District</span>
          <SettingsDropdown
            value={settings.rainfallDistrict}
            defaultOption={{ value: "__default__", label: "Default (HKO)" }}
            options={availableRainfallDistricts.map((d) => ({ value: d, label: d }))}
            onChange={(v) => updateSettings({ rainfallDistrict: v })}
          />
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
