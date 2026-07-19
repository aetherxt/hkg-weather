"use client";

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

  return (
    <nav
      className="weather-nav"
      aria-label="Primary navigation"
      data-active-page={activePage}
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
  );
}
