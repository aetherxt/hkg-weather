# Temporary Warnings Override

## Removing

Replaced with original one-liner on **2026-07-22**.

To restore if needed again: see [How to re-add](#how-to-re-add) below.

The mock was in `web/components/weather-dashboard.tsx` inside the `useState` initializer for `warningsSection`.

### What it provided

- **4 active warnings** (T8NE Tropical Cyclone, Red Rainstorm, Landslip Warning, Hot Weather Warning)
- **4 matching information details** with realistic content
- **2 special weather tips** (TC signal announcement, localised heavy rain)

### How to re-add

Replace the `warningsSection` useState one-liner:

```ts
const [warningsSection, setWarningsSection] = useState(() =>
  liveSection(initialWeather.warnings),
);
```

With the mock block:

```ts
const [warningsSection, setWarningsSection] = useState(() => {
    // TEMPORARY: mock warnings for styling the warnings panel
    return {
      status: "ready" as const,
      data: {
        summary: {
          WTCSGNL: {
            name: "Tropical Cyclone Warning Signal",
            code: "WTCSGNL",
            type: "8NE",
            actionCode: "ISSUE" as const,
            issueTime: "2026-07-22T06:00:00+08:00",
            updateTime: "2026-07-22T06:00:00+08:00",
            expireTime: "2026-07-22T12:00:00+08:00",
          },
          WRAIN: {
            name: "Rainstorm Warning Signal",
            code: "WRAIN",
            type: "Red",
            actionCode: "ISSUE" as const,
            issueTime: "2026-07-22T08:05:00+08:00",
            updateTime: "2026-07-22T08:05:00+08:00",
          },
          WL: {
            name: "Landslip Warning",
            code: "WL",
            actionCode: "ISSUE" as const,
            issueTime: "2026-07-22T07:45:00+08:00",
            updateTime: "2026-07-22T07:45:00+08:00",
            expireTime: "2026-07-23T07:45:00+08:00",
          },
          WHOT: {
            name: "Hot Weather Warning",
            code: "WHOT",
            actionCode: "ISSUE" as const,
            issueTime: "2026-07-22T06:30:00+08:00",
            updateTime: "2026-07-22T06:30:00+08:00",
          },
        },
        information: {
          details: [
            {
              contents: [
                "The Tropical Cyclone Warning Signal No. 8 Northeast is in force. Gale force winds are expected or blowing in Hong Kong with sustained speeds of 63 km/h or more.",
                "The public should take immediate precautions and stay indoors away from exposed windows and doors.",
              ],
              warningStatementCode: "WTCSGNL" as const,
              subtype: "8NE",
              updateTime: "2026-07-22T06:00:00+08:00",
            },
            {
              contents: [
                "The Red Rainstorm Warning was issued by the Hong Kong Observatory at 8:05 a.m. Heavy rain exceeding 100 mm per hour has been falling or is expected to fall over Hong Kong.",
                "Members of the public should stay in a safe place and avoid travelling. Those caught outdoors should seek shelter in a safe building.",
              ],
              warningStatementCode: "WRAIN" as const,
              subtype: "Red",
              updateTime: "2026-07-22T08:05:00+08:00",
            },
            {
              contents: [
                "The Landslip Warning was issued at 7:45 a.m. Persistent heavy rain has increased the risk of landslides. The public should stay away from steep slopes and retaining walls.",
              ],
              warningStatementCode: "WL" as const,
              updateTime: "2026-07-22T07:45:00+08:00",
            },
            {
              contents: [
                "The Hot Weather Warning was issued at 6:30 a.m. The Hong Kong Observatory forecasts very hot weather with maximum temperatures reaching 35 degrees Celsius or above.",
                "The public should take precautionary measures to avoid heat stroke and sunburn. Drink plenty of water and avoid prolonged outdoor activities.",
              ],
              warningStatementCode: "WHOT" as const,
              updateTime: "2026-07-22T06:30:00+08:00",
            },
          ],
        },
        specialWeatherTips: {
          swt: [
            {
              desc: "The Hong Kong Observatory announces that the Tropical Cyclone Warning Signal No. 8 is expected to be issued at or before 4:00 p.m. today (22 Jul 2026). Winds locally will strengthen further. The Government advises members of the public with long or difficult home journeys to begin their journeys now.",
              updateTime: "2026-07-22T14:00:00+08:00",
            },
            {
              desc: "Announcement on Localised Heavy Rain: More than 70 millimetres of rainfall were recorded in Tuen Mun District in the past 1 hour ending at 3:30 p.m. and may cause serious flooding.",
              updateTime: "2026-07-22T15:30:00+08:00",
            },
          ],
        },
      } satisfies Warnings,
      meta: {
        dataset: "warnings",
        sourceUpdatedAt: "2026-07-22T06:00:00Z" as string | null,
        fetchedAt: "2026-07-22T06:00:00Z" as string | null,
      },
      sourceUpdatedAt: "2026-07-22T06:00:00Z" as string | null,
      fetchedAt: "2026-07-22T06:00:00Z" as string | null,
    } as ReadyWeatherSection<Warnings>;
  });
```
