export interface EarthWeatherRasterHeader {
  version: number;
  multiplier1: number;
  multiplier2: number;
  north: number;
  west: number;
  south: number;
  east: number;
  longitudeStep: number;
  latitudeStep: number;
  width: number;
  height: number;
  minimumFirst: number;
  maximumFirst: number;
  minimumSecond: number;
  maximumSecond: number;
}

export interface EarthWeatherScalarGrid {
  header: EarthWeatherRasterHeader;
  values: Float32Array;
}

export interface EarthWeatherVectorGrid {
  header: EarthWeatherRasterHeader;
  u: Float32Array;
  v: Float32Array;
}

const HEADER_ROWS = 4;
const HEADER_UNIT_WIDTH = 4;
const HEADER_UNIT_HEIGHT = 4;
const PNG_SIGNATURE = "\u0089PNG\r\n\u001a\n";

function headerNumber(
  pixels: Uint8ClampedArray,
  index: number,
  imageWidth: number,
  version: number,
  unsigned = false,
) {
  let value = 0;
  const unitPixels = HEADER_UNIT_WIDTH * HEADER_UNIT_HEIGHT;
  for (let offset = 0; offset < unitPixels; offset += 1) {
    const pixel =
      Math.floor(offset / HEADER_UNIT_HEIGHT) * imageWidth +
      index * HEADER_UNIT_HEIGHT +
      offset % HEADER_UNIT_HEIGHT;
    const byte = pixel * 4;
    if (pixels[byte + 3] === 0) break;
    const shift = offset * 2;
    if (unsigned) {
      value +=
        pixels[byte] * 256 ** shift +
        pixels[byte + 1] * 256 ** (shift + 1) +
        pixels[byte + 2] * 256 ** (shift + 2);
    } else {
      const magnitude =
        pixels[byte] * 256 ** shift +
        pixels[byte + 1] * 256 ** (shift + 1);
      value += magnitude * (pixels[byte + 2] === 255 ? -1 : 1);
    }
    if (version === 0) break;
  }
  return value;
}

function finitePositive(value: number, name: string) {
  if (!Number.isFinite(value) || value <= 0) {
    throw new Error(`Earth Weather raster has invalid ${name}`);
  }
  return value;
}

function decodeHeader(
  pixels: Uint8ClampedArray,
  imageWidth: number,
  imageHeight: number,
): EarthWeatherRasterHeader {
  if (imageWidth < 64 || imageHeight <= HEADER_ROWS) {
    throw new Error("Earth Weather raster dimensions are invalid");
  }
  const version = headerNumber(pixels, 15, imageWidth, 0);
  const multiplier1 = finitePositive(
    headerNumber(pixels, 0, imageWidth, version),
    "coordinate multiplier",
  );
  const multiplier2 = finitePositive(
    headerNumber(pixels, 10, imageWidth, version),
    "value multiplier",
  );
  const header = {
    version,
    multiplier1,
    multiplier2,
    north: headerNumber(pixels, 1, imageWidth, version) / multiplier1,
    west: headerNumber(pixels, 2, imageWidth, version) / multiplier1,
    south: headerNumber(pixels, 3, imageWidth, version) / multiplier1,
    east: headerNumber(pixels, 4, imageWidth, version) / multiplier1,
    longitudeStep:
      headerNumber(pixels, 5, imageWidth, version) / multiplier1,
    latitudeStep:
      headerNumber(pixels, 6, imageWidth, version) / multiplier1,
    width: imageWidth,
    height: imageHeight - HEADER_ROWS,
    minimumFirst:
      headerNumber(pixels, 11, imageWidth, version) / multiplier2,
    maximumFirst:
      headerNumber(pixels, 12, imageWidth, version) / multiplier2,
    minimumSecond:
      headerNumber(pixels, 13, imageWidth, version) / multiplier2,
    maximumSecond:
      headerNumber(pixels, 14, imageWidth, version) / multiplier2,
  };
  if (
    !Number.isFinite(header.north) ||
    !Number.isFinite(header.south) ||
    !Number.isFinite(header.east) ||
    !Number.isFinite(header.west) ||
    header.north <= header.south ||
    header.east <= header.west
  ) {
    throw new Error("Earth Weather raster bounds are invalid");
  }
  finitePositive(header.longitudeStep, "longitude step");
  finitePositive(header.latitudeStep, "latitude step");
  return header;
}

async function imagePixels(url: string, signal?: AbortSignal) {
  const response = await fetch(url, {
    headers: { Accept: "image/png" },
    signal,
  });
  if (!response.ok) {
    throw new Error(`Earth Weather image returned HTTP ${response.status}`);
  }
  const bytes = await response.arrayBuffer();
  const signature = String.fromCharCode(
    ...new Uint8Array(bytes.slice(0, PNG_SIGNATURE.length)),
  );
  if (signature !== PNG_SIGNATURE) {
    throw new Error("Earth Weather image is not a PNG");
  }
  const blob = new Blob([bytes], { type: "image/png" });
  const bitmap = await createImageBitmap(blob);
  try {
    const canvas = document.createElement("canvas");
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    const context = canvas.getContext("2d", { willReadFrequently: true });
    if (!context) throw new Error("Canvas is unavailable");
    context.drawImage(bitmap, 0, 0);
    return context.getImageData(0, 0, bitmap.width, bitmap.height);
  } finally {
    bitmap.close();
  }
}

export async function decodeEarthWeatherRainfall(
  url: string,
  signal?: AbortSignal,
): Promise<EarthWeatherScalarGrid> {
  const image = await imagePixels(url, signal);
  const header = decodeHeader(image.data, image.width, image.height);
  const count = header.width * header.height;
  const values = new Float32Array(count);
  const start = HEADER_ROWS * image.width * 4;
  for (let index = 0; index < count; index += 1) {
    const pixel = start + index * 4;
    const encoded =
      image.data[pixel] +
      image.data[pixel + 1] * 256 +
      image.data[pixel + 2] * 65_536;
    values[index] = header.minimumFirst + encoded / header.multiplier2;
  }
  return { header, values };
}

export async function decodeEarthWeatherWind(
  url: string,
  signal?: AbortSignal,
): Promise<EarthWeatherVectorGrid> {
  const image = await imagePixels(url, signal);
  const header = decodeHeader(image.data, image.width, image.height);
  const count = header.width * header.height;
  const u = new Float32Array(count);
  const v = new Float32Array(count);
  const start = HEADER_ROWS * image.width * 4;
  const firstRange = header.maximumFirst - header.minimumFirst;
  const secondRange = header.maximumSecond - header.minimumSecond;
  if (
    !Number.isFinite(firstRange) ||
    !Number.isFinite(secondRange) ||
    firstRange <= 0 ||
    secondRange <= 0
  ) {
    throw new Error("Earth Weather wind ranges are invalid");
  }
  for (let index = 0; index < count; index += 1) {
    const pixel = start + index * 4;
    u[index] =
      header.minimumFirst + image.data[pixel] * firstRange / 255;
    v[index] =
      header.minimumSecond + image.data[pixel + 1] * secondRange / 255;
  }
  return { header, u, v };
}

export function sampleEarthWeatherVector(
  grid: EarthWeatherVectorGrid,
  longitude: number,
  latitude: number,
): [number, number] | null {
  const { header } = grid;
  const x = (longitude - header.west) / header.longitudeStep;
  const y = (header.north - latitude) / header.latitudeStep;
  const column = Math.floor(x);
  const row = Math.floor(y);
  if (
    column < 0 ||
    row < 0 ||
    column + 1 >= header.width ||
    row + 1 >= header.height
  ) {
    return null;
  }
  const xFraction = x - column;
  const yFraction = y - row;
  const northWest = row * header.width + column;
  const northEast = northWest + 1;
  const southWest = northWest + header.width;
  const southEast = southWest + 1;
  const interpolate = (values: Float32Array) =>
    values[northWest] * (1 - xFraction) * (1 - yFraction) +
    values[northEast] * xFraction * (1 - yFraction) +
    values[southWest] * (1 - xFraction) * yFraction +
    values[southEast] * xFraction * yFraction;
  const u = interpolate(grid.u);
  const v = interpolate(grid.v);
  return Number.isFinite(u) && Number.isFinite(v) ? [u, v] : null;
}
