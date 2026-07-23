import type { Metadata } from "next";
import { cookies } from "next/headers";
import { Geist, Geist_Mono } from "next/font/google";

import { SettingsProvider } from "@/lib/weather/settings";
import {
  parseSettingsCookie,
  SETTINGS_COOKIE_NAME,
} from "@/lib/weather/settings-values";
import { WeatherNav } from "@/components/weather-nav";

import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "HKG-Weather",
  description: "Detailed weather for Hong Kong.",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const cookieStore = await cookies();
  const initialSettings = parseSettingsCookie(
    cookieStore.get(SETTINGS_COOKIE_NAME)?.value,
  );

  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col">
        <SettingsProvider initialSettings={initialSettings}>
          {children}
          <WeatherNav />
        </SettingsProvider>
      </body>
    </html>
  );
}
