import { STAR_CATALOG } from "./stars";

export interface StarPosition {
  ra: number;
  dec: number;
  mag: number;
  name: string | null;
  altitude: number;
  azimuth: number;
  visible: boolean;
}

export function computeStarPositions(
  date: Date,
  lat: number,
  lng: number,
): StarPosition[] {
  const jd = julianDate(date);
  const gmst = greenwichMeanSiderealTime(jd);
  const lmst = ((gmst + lng) % 360 + 360) % 360;
  const latRad = (lat * Math.PI) / 180;

  return STAR_CATALOG.map((star) => {
    const ha = ((lmst - star.ra) % 360 + 360) % 360;
    const haRad = (ha * Math.PI) / 180;
    const decRad = (star.dec * Math.PI) / 180;

    const altRad = Math.asin(
      Math.sin(decRad) * Math.sin(latRad) +
        Math.cos(decRad) * Math.cos(latRad) * Math.cos(haRad),
    );
    const altDeg = (altRad * 180) / Math.PI;

    const x = -Math.sin(haRad) * Math.cos(decRad);
    const y =
      Math.sin(decRad) * Math.cos(latRad) -
      Math.cos(decRad) * Math.sin(latRad) * Math.cos(haRad);
    let azDeg = (Math.atan2(x, y) * 180) / Math.PI;
    azDeg = ((azDeg % 360) + 360) % 360;

    return {
      ra: star.ra,
      dec: star.dec,
      mag: star.mag,
      name: star.name,
      altitude: altDeg,
      azimuth: azDeg,
      visible: altDeg >= 0,
    };
  });
}

function julianDate(date: Date): number {
  const d = new Date(date);
  const year = d.getUTCFullYear();
  const month = d.getUTCMonth() + 1;
  const dayUTC =
    d.getUTCDate() +
    (d.getUTCHours() + d.getUTCMinutes() / 60 + d.getUTCSeconds() / 3600) /
      24;

  let y = year;
  let m = month;
  if (m <= 2) {
    y -= 1;
    m += 12;
  }
  const A = Math.floor(y / 100);
  const B = 2 - A + Math.floor(A / 4);
  return (
    Math.floor(365.25 * (y + 4716)) +
    Math.floor(30.6001 * (m + 1)) +
    dayUTC +
    B -
    1524.5
  );
}

function greenwichMeanSiderealTime(jd: number): number {
  const JC = (jd - 2451545.0) / 36525;
  let gmst =
    280.46061837 +
    360.98564736629 * (jd - 2451545.0) +
    0.000387933 * JC * JC -
    (JC * JC * JC) / 38710000;
  return ((gmst % 360) + 360) % 360;
}
