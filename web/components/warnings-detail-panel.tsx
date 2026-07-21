"use client";

import { activeWarnings, warningDisplayName } from "@/lib/weather";
import type { Warnings } from "@/lib/weather/types";

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString("en-HK", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Hong_Kong",
  });
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "numeric",
    timeZone: "Asia/Hong_Kong",
  });
}

function formatWarningTime(value: string, showDate: boolean) {
  return showDate
    ? `${formatDate(value)}, ${formatTime(value)}`
    : formatTime(value);
}

function warningTimeParts(value: string) {
  const d = new Date(value);
  const day = d.toLocaleDateString("en-GB", {
    day: "numeric",
    timeZone: "Asia/Hong_Kong",
  });
  const month = d.toLocaleDateString("en-GB", {
    month: "numeric",
    timeZone: "Asia/Hong_Kong",
  });
  return { date: `${Number(day)}/${Number(month)}` };
}

interface WarningsDetailPanelProps {
  warnings: Warnings;
}

export function WarningsDetailPanel({ warnings }: WarningsDetailPanelProps) {
  const entries = activeWarnings(warnings.summary);
  const details = warnings.information?.details ?? [];

  if (entries.length === 0) {
    return (
      <div className="wp-panel">
        <p className="wp-unavailable">No active warnings</p>
      </div>
    );
  }

  const warningDetailMap = new Map<string, (typeof details)[number]>();
  for (const detail of details) {
    const existing = warningDetailMap.get(detail.warningStatementCode);
    if (!existing || new Date(detail.updateTime) > new Date(existing.updateTime)) {
      warningDetailMap.set(detail.warningStatementCode, detail);
    }
  }

  return (
    <div className="wp-panel">
      {entries.map((warning) => {
        const detail = warningDetailMap.get(warning.code);
        const actionTime =
          warning.actionCode === "ISSUE"
            ? warning.issueTime
            : warning.actionCode === "UPDATE"
              ? warning.updateTime
              : undefined;
        const showDates = Boolean(
          actionTime &&
            warning.expireTime &&
            warningTimeParts(actionTime).date !==
              warningTimeParts(warning.expireTime).date,
        );

        return (
          <section className="wp-section" key={warning.code}>
            <div className="wp-section-header">
              <h3 className="wp-section-heading">
                {warningDisplayName(warning)}
              </h3>
              <span className="wp-action">{warning.actionCode}</span>
            </div>

            <div className="wp-times">
              {warning.actionCode === "ISSUE" && warning.issueTime ? (
                <span className="wp-time">
                  Issued {formatWarningTime(warning.issueTime, showDates)}
                </span>
              ) : null}
              {warning.actionCode === "UPDATE" ? (
                <span className="wp-time">
                  Updated {formatWarningTime(warning.updateTime, showDates)}
                </span>
              ) : null}
              {warning.actionCode === "REISSUE" ? (
                <span className="wp-time">
                  Re-issued {formatWarningTime(warning.updateTime, showDates)}
                </span>
              ) : null}
              {warning.expireTime ? (
                <span className="wp-time">
                  Expires {formatWarningTime(warning.expireTime, showDates)}
                </span>
              ) : null}
            </div>

            {detail?.contents ? (
              <ul className="wp-contents">
                {detail.contents.map((content, i) => (
                  <li className="wp-content" key={i}>
                    {content}
                  </li>
                ))}
              </ul>
            ) : null}
          </section>
        );
      })}
    </div>
  );
}
