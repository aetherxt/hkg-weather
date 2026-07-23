"use client";

import { useCallback, useRef, useState, useLayoutEffect } from "react";
import { useSettings } from "@/lib/weather/settings";
import { temperatureDisplayName } from "@/lib/weather/view-models";

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
  const [filter, setFilter] = useState("");
  const ref = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const selected = options.find((o) => o.value === value) ?? defaultOption;

  const handleSelect = useCallback(
    (v: string) => {
      onChange(v);
      setOpen(false);
      setFilter("");
    },
    [onChange],
  );

  useLayoutEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
        setFilter("");
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  useLayoutEffect(() => {
    if (open && inputRef.current) {
      inputRef.current.focus();
    }
  }, [open]);

  const allOptions = [defaultOption, ...options];
  const lowerFilter = filter.toLowerCase();
  const filteredOptions = allOptions.filter((o) =>
    o.label.toLowerCase().includes(lowerFilter),
  );

  return (
    <div className="settings-dropdown" ref={ref}>
      {open ? (
        <div className="settings-dropdown-input-wrapper">
          <input
            ref={inputRef}
            type="text"
            className="settings-dropdown-input"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                const first = filteredOptions[0];
                if (first) handleSelect(first.value);
              }
              if (e.key === "Escape") {
                setOpen(false);
                setFilter("");
              }
            }}
            placeholder={selected.label}
          />
          <svg className="settings-dropdown-arrow" width="10" height="6" viewBox="0 0 10 6" aria-hidden="true">
            <path d="M1 1l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
      ) : (
        <button
          className="settings-dropdown-trigger"
          type="button"
          onClick={() => setOpen(true)}
          aria-expanded={open}
        >
          <span>{selected.label}</span>
          <svg className="settings-dropdown-arrow" width="10" height="6" viewBox="0 0 10 6" aria-hidden="true">
            <path d="M1 1l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      )}
      {open && (
        <ul className="settings-dropdown-list" role="listbox">
          {filteredOptions.length > 0 ? (
            filteredOptions.map((opt) => (
              <li
                key={opt.value}
                className={`settings-dropdown-option${opt.value === selected.value ? " settings-dropdown-option-selected" : ""}`}
                role="option"
                aria-selected={opt.value === selected.value}
                onClick={() => handleSelect(opt.value)}
              >
                {opt.label}
              </li>
            ))
          ) : (
            <li className="settings-dropdown-option settings-dropdown-no-results" role="option" aria-disabled>
              No matches
            </li>
          )}
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
            options={availableTemperatureStations.map((s) => ({ value: s, label: temperatureDisplayName(s) }))}
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
