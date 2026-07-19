export type IsoDateTime = string;

export interface ResponseMetadata {
  dataset: string;
  sourceUpdatedAt: IsoDateTime | null;
  fetchedAt: IsoDateTime | null;
}

export interface ListResponseMetadata extends ResponseMetadata {
  count: number;
}

export interface DataResponse<Data> {
  data: Data;
  meta: ResponseMetadata;
}

export interface ListResponse<Item> {
  data: Item[];
  meta: ListResponseMetadata;
}

export interface ValidationIssue {
  type?: string;
  loc?: Array<string | number>;
  msg?: string;
  input?: unknown;
  [key: string]: unknown;
}

export type WeatherErrorDetail = string | ValidationIssue[];

export interface ValueUnit<Unit extends string> {
  value: number;
  unit: Unit;
}

export interface PlaceValue<Unit extends string> extends ValueUnit<Unit> {
  place: string;
}

export interface TimedPlaceValues<Unit extends string> {
  data: Array<PlaceValue<Unit>>;
  recordTime: IsoDateTime;
}

export interface LightningReading {
  place: string;
  occur: "true" | "false";
}

export interface LightningObservations {
  data: LightningReading[];
  startTime: IsoDateTime;
  endTime: IsoDateTime;
}

export interface DistrictRainfallReading {
  unit: "mm";
  place: string;
  max: number;
  min?: number;
  main: "TRUE" | "FALSE";
}

export interface DistrictRainfallObservations {
  data: DistrictRainfallReading[];
  startTime: IsoDateTime;
  endTime: IsoDateTime;
}

export interface StationRainfallReading {
  automaticWeatherStation: string;
  automaticWeatherStationID: string;
  value: string;
  unit: "mm";
}

export interface StationRainfallResponse {
  observationTime: IsoDateTime;
  hourlyRainfall: StationRainfallReading[];
}

export interface UvIndexReading {
  place: string;
  value: number;
  desc?: string;
}

export interface UvIndexObservations {
  data: UvIndexReading[];
  recordDesc?: string;
}

export interface CurrentWeather {
  lightning?: LightningObservations;
  rainfall?: DistrictRainfallObservations;
  icon: number[];
  iconUpdateTime?: IsoDateTime;
  uvindex?: UvIndexObservations;
  temperature?: TimedPlaceValues<"C">;
  humidity?: TimedPlaceValues<"percent">;
  updateTime: IsoDateTime;
  warningMessage?: string | string[];
  rainstormReminder?: string | string[];
  specialWxTips?: string[];
  tcmessage?: string | string[];
  mintempFrom00To09?: string;
  rainfallFrom00To12?: string;
  rainfallLastMonth?: string;
  rainfallJanuaryToLastMonth?: string;
}

export interface LocalForecast {
  generalSituation: string;
  tcInfo: string;
  fireDangerWarning: string;
  forecastPeriod: string;
  forecastDesc: string;
  outlook: string;
  updateTime: IsoDateTime;
}

export type ProbabilityOfSignificantRain =
  | "High"
  | "Medium High"
  | "Medium"
  | "Medium Low"
  | "Low";

export interface DailyForecast {
  forecastDate: string;
  week: string;
  forecastWind: string;
  forecastWeather: string;
  forecastMaxtemp: ValueUnit<"C">;
  forecastMintemp: ValueUnit<"C">;
  forecastMaxrh: ValueUnit<"percent">;
  forecastMinrh: ValueUnit<"percent">;
  ForecastIcon: number;
  PSR: ProbabilityOfSignificantRain;
}

export interface SeaTemperature extends PlaceValue<"C"> {
  recordTime: IsoDateTime;
}

export interface SoilTemperature extends SeaTemperature {
  depth: ValueUnit<"metre">;
}

export interface NineDayForecast {
  generalSituation: string;
  weatherForecast: DailyForecast[];
  updateTime: IsoDateTime;
  seaTemp?: SeaTemperature;
  soilTemp?: SoilTemperature[];
}

export type WarningActionCode =
  | "ISSUE"
  | "REISSUE"
  | "CANCEL"
  | "EXTEND"
  | "UPDATE";

export type WarningStatementCode =
  | "WFIRE"
  | "WFROST"
  | "WHOT"
  | "WCOLD"
  | "WMSGNL"
  | "WTCPRE8"
  | "WRAIN"
  | "WFNTSA"
  | "WL"
  | "WTCSGNL"
  | "WTMW"
  | "WTS";

export interface WarningSummaryItem {
  name: string;
  code: string;
  type?: string;
  actionCode: WarningActionCode;
  issueTime?: IsoDateTime;
  expireTime?: IsoDateTime;
  updateTime: IsoDateTime;
}

export type WarningSummary = Record<string, WarningSummaryItem>;

export interface WarningDetail {
  contents: string[];
  warningStatementCode: WarningStatementCode;
  subtype?: string;
  updateTime: IsoDateTime;
}

export interface WarningInformation {
  details: WarningDetail[];
}

export interface SpecialWeatherTip {
  desc: string;
  updateTime: IsoDateTime;
}

export interface SpecialWeatherTips {
  swt: SpecialWeatherTip[];
}

export interface Warnings {
  summary: WarningSummary;
  information: WarningInformation;
  specialWeatherTips: SpecialWeatherTips;
}

export interface TemperatureReading {
  observedAt: IsoDateTime;
  station: string;
  temperatureC: number | null;
}

export interface WindReading {
  observedAt: IsoDateTime;
  station: string;
  meanWindDirection: string | null;
  meanWindSpeedKmh: number | null;
  maximumGustKmh: number | null;
}

export interface LamppostReading {
  lamppostId: string;
  deviceId: string;
  label: string;
  latitude: number;
  longitude: number;
  reading: Record<string, unknown>;
}

export interface AstronomicalTimes {
  date: string;
  sunrise: string;
  sunTransit: string;
  sunset: string;
  moonrise: string | null;
  moonTransit: string | null;
  moonset: string | null;
}

export interface RegionalObservations {
  temperature: ListResponse<TemperatureReading>;
  wind: ListResponse<WindReading>;
}
