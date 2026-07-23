import type { Metadata } from "next";

import { TyphoonTrackPage } from "@/components/typhoon-track-page";

export const metadata: Metadata = {
  title: "Typhoon | HKG-Weather",
};

export default function Typhoon() {
  return <TyphoonTrackPage />;
}
