import type { WarningSummary, WarningSummaryItem } from "./types.ts";

export function warningDisplayName(warning: WarningSummaryItem): string {
  const code = warning.code;
  const t = warning.type;

  if (code.startsWith("WRAIN") && t) {
    return `${t} Rainstorm`;
  }

  if (code === "WTCSGNL" && t) {
    return `T${t} Tropical Cyclone`;
  }

  if (code === "WFIRE" && t) {
    return `${t} Fire Danger`;
  }

  if (code === "WFNTSA") {
    return "Flooding in NNT";
  }

  if (code === "WTCPRE8") {
    return "T8 Planned";
  }

  return warning.name;
}

export function activeWarnings(summary: WarningSummary): WarningSummaryItem[] {
  return Object.values(summary).filter((w) => w.actionCode !== "CANCEL");
}

export function activeWarningCount(summary: WarningSummary): number {
  return activeWarnings(summary).length;
}

export function warningSummaryHeadline(summary: WarningSummary): string {
  const count = activeWarningCount(summary);
  if (count === 0) return "No warnings in force";
  return `${count} ${count === 1 ? "warning" : "warnings"} in force`;
}
