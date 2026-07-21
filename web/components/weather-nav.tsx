"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { WeatherClouds } from "@/components/weather-clouds";

const navigationItems = [
  { href: "/", label: "Current", page: "home" },
  { href: "/forecast", label: "Forecast", page: "forecast" },
] as const;

export function WeatherNav() {
  const pathname = usePathname();
  const activePage = pathname.startsWith("/forecast") ? "forecast" : "home";
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const revealZoneHeight = 130;

    const handlePointerMove = (event: PointerEvent) => {
      const revealThreshold = window.innerHeight - revealZoneHeight;
      setIsVisible(event.clientY >= revealThreshold);
    };

    const handlePointerLeave = () => {
      setIsVisible(false);
    };

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerleave", handlePointerLeave);

    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerleave", handlePointerLeave);
    };
  }, [pathname]);

  return (
    <>
      <div className="weather-nav-reveal-zone" aria-hidden="true" />

      <nav
        className="weather-nav"
        aria-label="Primary navigation"
        data-active-page={activePage}
        data-visible={isVisible ? "true" : undefined}
        onBlurCapture={() => setIsVisible(false)}
        onFocusCapture={() => setIsVisible(true)}
        onPointerEnter={() => setIsVisible(true)}
        onPointerLeave={() => setIsVisible(false)}
      >
        <WeatherClouds />

        <div className="weather-nav-track">
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
    </>
  );
}
