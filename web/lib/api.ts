// Browser-side client. NEXT_PUBLIC_API_BASE_URL is inlined at build time and
// must be reachable from the *browser* (localhost + published port), never
// the compose service name (spec/00-architecture.md §10).
import type {
  CitiesResponse,
  DailyResponse,
  DatesResponse,
  HealthResponse,
  HistoryResponse,
  LatestResponse,
  RevisionsResponse,
  ApiErrorBody,
} from "./types";

export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000").replace(/\/+$/, "");

export type ApiErrorKind = "network" | "not_found" | "client" | "server";

export class ApiError extends Error {
  constructor(
    public readonly kind: ApiErrorKind,
    public readonly status: number | null,
    public readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type Params = Record<string, string | number | null | undefined>;

async function apiGet<T>(path: string, params: Params, signal?: AbortSignal): Promise<T> {
  const url = new URL(API_BASE_URL + path);
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, String(value));
  }
  let res: Response;
  try {
    res = await fetch(url.toString(), { signal, headers: { Accept: "application/json" } });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError("network", null, "NETWORK", `Could not reach the API at ${API_BASE_URL}.`);
  }
  if (res.ok) return (await res.json()) as T;

  let body: ApiErrorBody | null = null;
  try {
    body = (await res.json()) as ApiErrorBody;
  } catch {
    body = null;
  }
  const code = body?.error?.code ?? `HTTP_${res.status}`;
  const message = body?.error?.message ?? `${res.status} ${res.statusText}`;
  const kind: ApiErrorKind = res.status === 404 ? "not_found" : res.status >= 500 ? "server" : "client";
  throw new ApiError(kind, res.status, code, message);
}

export const api = {
  cities: (signal?: AbortSignal) => apiGet<CitiesResponse>("/cities", {}, signal),
  latest: (city: string, horizonHours: number, signal?: AbortSignal) =>
    apiGet<LatestResponse>("/forecasts/latest", { city, granularity: "HOURLY", horizon_hours: horizonHours }, signal),
  revisions: (city: string, horizonHours: number, signal?: AbortSignal) =>
    apiGet<RevisionsResponse>("/forecasts/revisions", { city, horizon_hours: horizonHours }, signal),
  history: (city: string, targetTime: string, signal?: AbortSignal) =>
    apiGet<HistoryResponse>("/forecasts/history", { city, target_time: targetTime }, signal),
  dates: (city: string, signal?: AbortSignal) => apiGet<DatesResponse>("/forecasts/dates", { city }, signal),
  daily: (city: string, dateForecastMade: string | null, signal?: AbortSignal) =>
    apiGet<DailyResponse>("/forecasts/daily", { city, date_forecast_made: dateForecastMade }, signal),
  health: (city: string, signal?: AbortSignal) => apiGet<HealthResponse>("/ingestion/health", { city }, signal),
};
