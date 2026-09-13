"use client";

import { useEffect, useState } from "react";

import { DailyMatrix } from "@/components/daily-matrix";
import { ForecastEvolution } from "@/components/forecast-evolution";
import { HourlyForecast } from "@/components/hourly-forecast";
import { IngestionHealth } from "@/components/ingestion-health";
import { StateBoundary } from "@/components/state-boundary";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { API_BASE_URL, api } from "@/lib/api";
import { useApi } from "@/lib/use-api";

const HORIZONS = [
  { hours: 24, label: "Next 24 hours" },
  { hours: 48, label: "Next 48 hours" },
  { hours: 72, label: "Next 3 days" },
  { hours: 168, label: "Next 7 days" },
];

/**
 * Control -> request mapping (spec/01-dashboard.md §15):
 *   city            -> revisions, latest (moment picker options), dates + daily,
 *                      ingestion health; resets the moment and the forecast date
 *   horizon         -> revisions only (pane i)
 *   moment          -> history only (pane ii)
 *   forecast date   -> daily only (View B)
 */
export function Dashboard() {
  const cities = useApi((signal) => api.cities(signal), [], (d) => d.cities.length === 0);
  const [city, setCity] = useState<string | null>(null);
  const [horizon, setHorizon] = useState<number>(48);
  const [targetTime, setTargetTime] = useState<string | null>(null);
  const [forecastDate, setForecastDate] = useState<string | null>(null);

  useEffect(() => {
    if (city === null && cities.data) setCity(cities.data.cities[0].id);
  }, [cities.data, city]);

  const selectCity = (id: string) => {
    setCity(id);
    setTargetTime(null);
    setForecastDate(null);
  };

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Belgian Weather Explorer</h1>
          <p className="text-sm text-muted-foreground">
            Open-Meteo forecasts and how they were revised. API: <span className="font-mono">{API_BASE_URL}</span>
          </p>
        </div>
        <div className="flex flex-col gap-3 sm:flex-row">
          <div className="w-full sm:w-48">
            <label className="mb-1 block text-xs font-medium text-muted-foreground">City</label>
            <Select value={city ?? ""} onValueChange={selectCity} disabled={cities.status !== "ok"}>
              <SelectTrigger aria-label="City">
                <SelectValue placeholder={cities.status === "loading" ? "Loading…" : "City"} />
              </SelectTrigger>
              <SelectContent>
                {(cities.data?.cities ?? []).map((c) => (
                  <SelectItem key={c.id} value={c.id}>
                    {c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="w-full sm:w-48">
            <label className="mb-1 block text-xs font-medium text-muted-foreground">Horizon</label>
            <Select value={String(horizon)} onValueChange={(v) => setHorizon(Number(v))}>
              <SelectTrigger aria-label="Horizon">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {HORIZONS.map((h) => (
                  <SelectItem key={h.hours} value={String(h.hours)}>
                    {h.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      </header>

      <StateBoundary
        state={cities}
        skeleton={
          <div className="space-y-6">
            <Skeleton className="h-96 w-full" />
            <Skeleton className="h-40 w-full" />
          </div>
        }
        empty={{ title: "No cities are configured.", hint: "Add at least three cities to config/cities.json and restart." }}
      >
        {() =>
          city ? (
            <div className="space-y-6">
              <HourlyForecast city={city} horizonHours={horizon} />
              <ForecastEvolution city={city} targetTime={targetTime} onTargetTimeChange={setTargetTime} />
              <IngestionHealth city={city} />
              <DailyMatrix city={city} forecastDate={forecastDate} onForecastDateChange={setForecastDate} />
            </div>
          ) : null
        }
      </StateBoundary>
    </div>
  );
}
