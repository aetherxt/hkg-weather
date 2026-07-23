import type { WarningSummary } from "@/lib/weather";
import { warningDisplayName } from "@/lib/weather";
import { type KeyboardEvent } from "react";

import type { WeatherDetailInteractionProps } from "@/components/weather-detail-sections";

function formatUpdatedAt(iso: string) {
  const date = new Date(iso);
  const now = new Date();
  const hkTime = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Hong_Kong",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(date);
  const todayHk = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Hong_Kong",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
  const timePart = date.toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: "Asia/Hong_Kong",
  });
  if (hkTime === todayHk) {
    return timePart;
  }
  const datePart = date.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "numeric",
    timeZone: "Asia/Hong_Kong",
  });
  return `${datePart}, ${timePart}`;
}

interface WeatherWarningsProps extends WeatherDetailInteractionProps {
  warnings: WarningSummary;
  updatedAt: string | null;
}

const warningTimeFormatter = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
  timeZone: "Asia/Hong_Kong",
});

function warningTimeParts(value: string) {
  const parts = warningTimeFormatter.formatToParts(new Date(value));
  const part = (type: string) =>
    parts.find((candidate) => candidate.type === type)?.value ?? "";

  return {
    date: `${Number(part("day"))}/${Number(part("month"))}`,
    time: `${part("hour").padStart(2, "0")}:${part("minute")}`,
  };
}

function formatWarningTime(value: string, showDate: boolean) {
  const { date, time } = warningTimeParts(value);
  return showDate ? `${date}, ${time}` : time;
}

export function WeatherWarnings({
  warnings,
  updatedAt,
  activeSection,
  onSelectSection,
}: WeatherWarningsProps) {
  const warningEntries = Object.entries(warnings).filter(
    ([, warning]) => warning.actionCode !== "CANCEL",
  );
  const visible = warningEntries.slice(0, 2);
  const hasMore = warningEntries.length > 2;

  if (warningEntries.length === 0) {
    return (
      <section
        className="weather-warnings weather-warnings-empty"
        aria-labelledby="weather-warnings-title"
      >
        <div className="weather-warnings-row">
          <div className="weather-warnings-content">
            <div className="weather-warnings-heading-row">
              <h2 className="weather-warnings-title" id="weather-warnings-title">
                Warnings
              </h2>
              {updatedAt && (
                <span className="weather-warnings-updated-at">
                  Last Updated At: {formatUpdatedAt(updatedAt)}
                </span>
              )}
            </div>
            <p className="weather-no-warnings">No Warnings</p>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section className="weather-warnings" aria-labelledby="weather-warnings-title">
      <div
        className="weather-warnings-row weather-data-trigger"
        data-weather-trigger="warnings"
        data-active={activeSection === "warnings" ? "true" : undefined}
        aria-controls="weather-detail-warnings-content"
        aria-expanded={activeSection === "warnings"}
        aria-label="Open warning details"
        onClick={() => onSelectSection("warnings")}
        onKeyDown={(event: KeyboardEvent<HTMLDivElement>) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            onSelectSection("warnings");
          }
        }}
        role="button"
        tabIndex={0}
      >
        <div className="weather-warnings-content">
          <div className="weather-warnings-heading-row">
            <h2 className="weather-warnings-title" id="weather-warnings-title">
              Warnings
            </h2>
            {updatedAt && (
              <span className="weather-warnings-updated-at">
                Last Updated At: {formatUpdatedAt(updatedAt)}
              </span>
            )}
            <span className="weather-row-chevron" aria-hidden="true" />
          </div>
          <ul className="weather-warning-list">
            {visible.map(([category, warning]) => {
              const actionTime =
                warning.actionCode === "ISSUE"
                  ? warning.issueTime
                  : warning.actionCode === "UPDATE" || warning.actionCode === "REISSUE"
                    ? warning.updateTime
                    : undefined;
              const showDates = Boolean(
                actionTime &&
                  warning.expireTime &&
                  warningTimeParts(actionTime).date !==
                    warningTimeParts(warning.expireTime).date,
              );

              return (
                <li className="weather-warning" key={category}>
                  <p className="weather-warning-name">{warningDisplayName(warning)}</p>
                  <p className="weather-warning-meta">
                    <span className="weather-warning-action">
                      {warning.actionCode}
                    </span>
                    {warning.actionCode === "ISSUE" && warning.issueTime ? (
                      <>
                        <span aria-hidden="true">·</span>
                        Issued {formatWarningTime(warning.issueTime, showDates)}
                      </>
                    ) : null}
                    {warning.actionCode === "UPDATE" ? (
                      <>
                        <span aria-hidden="true">·</span>
                        Updated {formatWarningTime(warning.updateTime, showDates)}
                      </>
                    ) : null}
                    {warning.actionCode === "REISSUE" ? (
                      <>
                        <span aria-hidden="true">·</span>
                        Re-issued {formatWarningTime(warning.updateTime, showDates)}
                      </>
                    ) : null}
                    {warning.expireTime ? (
                      <>
                        <span aria-hidden="true">·</span>
                        Expires {formatWarningTime(warning.expireTime, showDates)}
                      </>
                    ) : null}
                  </p>
                </li>
              );
            })}
          </ul>
          {hasMore && (
            <p className="weather-warnings-more">...More</p>
          )}
        </div>
      </div>
    </section>
  );
}
