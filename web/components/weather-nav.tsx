"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

declare global {
  interface Window {
    __HOVER_Y__?: number;
  }
}

import { WeatherClouds } from "@/components/weather-clouds";
import { SettingsPopup } from "@/components/settings-popup";

const navigationItems = [
  { href: "/", label: "Current", page: "home" },
  { href: "/forecast", label: "Forecast", page: "forecast" },
] as const;

export function WeatherNav() {
  const pathname = usePathname();
  const activePage = pathname.startsWith("/forecast") ? "forecast" : "home";
  const [isVisible, setIsVisible] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const showSettingsRef = useRef(false);
  const [hoveredItem, setHoveredItem] = useState<string | null>(null);
  const navRef = useRef<HTMLElement>(null);

  const toggleSettings = useCallback(() => {
    setShowSettings((v) => {
      const next = !v;
      showSettingsRef.current = next;
      return next;
    });
  }, []);

  const closeSettings = useCallback(() => {
    showSettingsRef.current = false;
    setShowSettings(false);
  }, []);

  useLayoutEffect(() => {
    const nav = navRef.current;
    if (!nav) return;

    const target = showSettings ? "gear" : (hoveredItem ?? activePage);
    const button = target === "gear"
      ? nav.querySelector<HTMLElement>(".weather-nav-settings")
      : nav.querySelector<HTMLElement>(`[data-page="${target}"]`);

    if (!button) {
      nav.style.removeProperty("--active-opacity");
      return;
    }

    nav.style.setProperty("--active-left", `${button.offsetLeft}px`);
    nav.style.setProperty("--active-width", `${button.offsetWidth}px`);
    nav.style.setProperty("--active-opacity", "1");
  }, [hoveredItem, activePage, showSettings]);

  const handlePointerMove = useCallback((e: React.PointerEvent) => {
    const target = (e.target as HTMLElement).closest(
      ".weather-nav-settings, [data-page]",
    );
    if (target) {
      if (target.classList.contains("weather-nav-settings")) {
        setHoveredItem("gear");
      } else {
        setHoveredItem(target.getAttribute("data-page"));
      }
    } else {
      setHoveredItem(null);
    }
  }, []);

  const handlePointerLeave = useCallback(() => {
    setHoveredItem(null);
  }, []);

  useEffect(() => {
    const revealZoneHeight = 130;

    const handlePointerMove = (event: PointerEvent) => {
      window.__HOVER_Y__ = event.clientY;
      const revealThreshold = window.innerHeight - revealZoneHeight;
      if (showSettingsRef.current) return;
      setIsVisible(event.clientY >= revealThreshold);
    };

    const handlePointerLeave = () => {
      if (!showSettingsRef.current) setIsVisible(false);
    };

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerleave", handlePointerLeave);

    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerleave", handlePointerLeave);
    };
  }, [pathname]);

  useEffect(() => {
    if (showSettings) {
      setIsVisible(true);
    } else {
      const revealZoneHeight = 130;
      const revealThreshold = window.innerHeight - revealZoneHeight;
      setIsVisible((window.__HOVER_Y__ ?? window.innerHeight) >= revealThreshold);
    }
  }, [showSettings]);

  return (
    <>
      <div className="weather-nav-reveal-zone" aria-hidden="true" />

      <nav
        className="weather-nav"
        ref={navRef}
        aria-label="Primary navigation"
        data-active-page={activePage}
        data-visible={isVisible ? "true" : undefined}
        onBlurCapture={() => { if (!showSettings) setIsVisible(false); }}
        onFocusCapture={() => setIsVisible(true)}
        onPointerEnter={() => setIsVisible(true)}
        onPointerLeave={(e) => {
          if (!showSettings) setIsVisible(false);
          handlePointerLeave();
        }}
      >
        <WeatherClouds />

        <div
          className="weather-nav-track"
          onPointerMove={handlePointerMove}
          onPointerLeave={handlePointerLeave}
          onClick={(e) => {
            if ((e.target as HTMLElement).closest("[data-page]")) {
              closeSettings();
            }
          }}
        >
          <button
            className="weather-nav-settings"
            aria-label="Open settings"
            onClick={toggleSettings}
            type="button"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="3"/>
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
            </svg>
          </button>

          <span className="weather-nav-selector" aria-hidden="true" />

          {navigationItems.map((item) => {
            const isActive =
              item.href === "/"
                ? pathname === item.href
                : pathname.startsWith(item.href);

            return (
              <Link
                className="weather-nav-link"
                href={item.href}
                data-page={item.page}
                aria-current={isActive ? "page" : undefined}
                key={item.href}
              >
                {item.label}
              </Link>
            );
          })}
        </div>
      </nav>

      {showSettings && <SettingsPopup onClose={closeSettings} />}
    </>
  );
}
