// Mirrors api/app/schemas.py. All timestamps are ISO 8601 UTC ("...Z").

export interface City {
  id: string;
  name: string;
  lat: number;
  lon: number;
}
export interface CitiesResponse {
  cities: City[];
}

export interface ForecastRun {
  forecast_run_id: number;
  city: string;
  date_forecast_made: string; // YYYY-MM-DD
  fetched_at: string;
  source: string;
}

export interface HourlyPoint {
  target_time: string;
  temperature_2m: number | null;
  precipitation: number | null;
  precipitation_probability: number | null;
  visibility: number | null;
  wind_gusts_10m: number | null;
}

export interface LatestResponse {
  run: ForecastRun;
  granularity: "HOURLY" | "DAILY";
  horizon_hours: number;
  window_start: string;
  window_end: string;
  points: HourlyPoint[]; // the dashboard only requests HOURLY
}

export interface RevisionSeries {
  forecast_run_id: number;
  date_forecast_made: string;
  fetched_at: string;
  points: HourlyPoint[];
}
export interface RevisionsResponse {
  city: string;
  horizon_hours: number;
  window_start: string;
  window_end: string;
  target_times: string[];
  series: RevisionSeries[]; // newest issue first
}

export interface HistoryEntry extends HourlyPoint {
  forecast_run_id: number;
  date_forecast_made: string;
  fetched_at: string;
  was_future_at_fetch: boolean;
}
export interface HistoryResponse {
  city: string;
  target_time: string;
  revisions: HistoryEntry[]; // oldest issue first
}

export interface DailyPoint {
  target_date: string;
  uv_index_max: number | null;
  temperature_2m_max: number | null;
  wind_gusts_10m_max: number | null;
  sunshine_duration: number | null; // seconds
  visibility_min: number | null; // metres, derived from hourly rows
}
export interface DailyResponse {
  run: ForecastRun;
  points: DailyPoint[];
}

export interface DatesResponse {
  city: string;
  dates: string[]; // newest first
}

export type IngestStatus = "SUCCESS" | "TIMEOUT" | "MALFORMED" | "DB_ERROR";
export interface IngestRun {
  run_id: string;
  status: IngestStatus;
  rows_written: number | null;
  error_detail: string | null;
  started_at: string;
  finished_at: string;
}
export interface CityHealth {
  city: string;
  healthy: boolean;
  last_attempt: IngestRun | null;
  last_success: IngestRun | null;
}
export interface HealthResponse {
  generated_at: string;
  cities: CityHealth[];
}

export interface ApiErrorBody {
  error: { code: string; message: string; status: number };
}
