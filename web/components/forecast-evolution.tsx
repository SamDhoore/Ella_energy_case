"use client";

import { useEffect, useMemo } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { StateBoundary } from "@/components/state-boundary";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { fmtDate, fmtDateTime, fmtNum } from "@/lib/format";
import { METRICS, PALETTE, type Metric } from "@/lib/metrics";
import type { HistoryEntry, HistoryResponse } from "@/lib/types";
import { useApi } from "@/lib/use-api";

const PICKER_HORIZON_HOURS = 168; // everything the latest issue can hold ahead of now

interface Props {
  city: string;
  targetTime: string | null;
  onTargetTimeChange: (value: string | null) => void;
}

/**
 * Pane (ii): pick one moment, see how every forecast issue predicted it.
 * Picker options are the hours the *latest* issue actually holds
 * (GET /forecasts/latest); the series comes from GET /forecasts/history.
 */
export function ForecastEvolution({ city, targetTime, onTargetTimeChange }: Props) {
  const options = useApi(
    (signal) => api.latest(city, PICKER_HORIZON_HOURS, signal),
    [city],
    (d) => d.points.length === 0,
  );
  const history = useApi(
    targetTime ? (signal) => api.history(city, targetTime, signal) : null,
    [city, targetTime],
    (d) => d.revisions.length === 0,
  );

  const hoursByDate = useMemo(() => {
    const map = new Map<string, string[]>();
    for (const p of options.data?.points ?? []) {
      const day = p.target_time.slice(0, 10);
      map.set(day, [...(map.get(day) ?? []), p.target_time]);
    }
    return map;
  }, [options.data]);

  // Default moment: tomorrow 12:00 UTC if the latest issue holds it, else the first hour.
  useEffect(() => {
    if (targetTime !== null || !options.data) return;
    const times = options.data.points.map((p) => p.target_time);
    const noon = new Date();
    noon.setUTCDate(noon.getUTCDate() + 1);
    noon.setUTCHours(12, 0, 0, 0);
    const iso = noon.toISOString().replace(".000Z", "Z");
    onTargetTimeChange(times.includes(iso) ? iso : (times[0] ?? null));
  }, [options.data, targetTime, onTargetTimeChange]);

  const selectedDate = targetTime?.slice(0, 10) ?? "";
  const hoursForDate = hoursByDate.get(selectedDate) ?? [];

  const selectDate = (day: string) => {
    const hours = hoursByDate.get(day) ?? [];
    const sameHour = hours.find((t) => t.slice(11, 16) === targetTime?.slice(11, 16));
    onTargetTimeChange(sameHour ?? hours[0] ?? null);
  };

  return (
    <Card>
      <CardHeader className="gap-3 lg:flex-row lg:items-start lg:justify-between lg:space-y-0">
        <div className="space-y-1.5">
          <CardTitle>Forecast evolution for one moment</CardTitle>
          <CardDescription>
            How each forecast issue predicted the chosen hour. Newest issue on the left; hollow dots are issues fetched
            after the hour had passed (observation, not prediction). Times in UTC.
          </CardDescription>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row">
          <Select value={selectedDate} onValueChange={selectDate} disabled={options.status !== "ok"}>
            <SelectTrigger className="w-full sm:w-44" aria-label="Target date">
              <SelectValue placeholder={options.status === "loading" ? "Loading…" : "Date"} />
            </SelectTrigger>
            <SelectContent>
              {[...hoursByDate.keys()].map((day) => (
                <SelectItem key={day} value={day}>
                  {fmtDate(day)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select
            value={targetTime ?? ""}
            onValueChange={(v) => onTargetTimeChange(v || null)}
            disabled={options.status !== "ok" || hoursForDate.length === 0}
          >
            <SelectTrigger className="w-full sm:w-32" aria-label="Target hour">
              <SelectValue placeholder="Hour" />
            </SelectTrigger>
            <SelectContent>
              {hoursForDate.map((t) => (
                <SelectItem key={t} value={t}>
                  {t.slice(11, 16)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        <StateBoundary
          state={options}
          skeleton={<Skeleton className="h-64 w-full" />}
          empty={{
            title: `No forecast data yet for ${city}.`,
            hint: "Check the ingestion health panel: the first ingest may still be running or may have failed.",
          }}
        >
          {() => (
            <StateBoundary
              state={history}
              idle={<Skeleton className="h-64 w-full" />}
              skeleton={<Skeleton className="h-64 w-full" />}
              empty={{ title: "No forecast issue holds a value for that moment." }}
            >
              {(data) => <EvolutionCharts data={data} />}
            </StateBoundary>
          )}
        </StateBoundary>
      </CardContent>
    </Card>
  );
}

interface Row {
  issue: string; // date_forecast_made, the x axis
  fetched_at: string;
  was_future_at_fetch: boolean;
  value: number | null;
}

function EvolutionCharts({ data }: { data: HistoryResponse }) {
  // API returns oldest issue first; the pane reads newest -> oldest, left to right.
  const newestFirst = useMemo(() => [...data.revisions].reverse(), [data.revisions]);
  return (
    <>
      <p className="text-xs text-muted-foreground">
        {fmtDateTime(data.target_time)} UTC · {newestFirst.length} {newestFirst.length === 1 ? "issue" : "issues"}
        {newestFirst.length === 1 ? " (more points appear once a second daily ingest has run)" : ""}
      </p>
      {METRICS.map((metric) => (
        <MetricEvolution key={metric.key} entries={newestFirst} metric={metric} />
      ))}
    </>
  );
}

function MetricEvolution({ entries, metric }: { entries: HistoryEntry[]; metric: Metric }) {
  const rows: Row[] = entries.map((e) => ({
    issue: e.date_forecast_made,
    fetched_at: e.fetched_at,
    was_future_at_fetch: e.was_future_at_fetch,
    value: e[metric.key],
  }));
  const latest = rows[0];
  const color = PALETTE[1];

  return (
    <div>
      <h3 className="mb-1 text-sm font-medium">
        {metric.label}{" "}
        <span className="text-muted-foreground">
          — latest {fmtNum(latest.value, metric.digits, ` ${metric.unit}`)}, issued {fmtDate(latest.issue)}
        </span>
      </h3>
      <div className="h-48 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 12, right: 24, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
            <XAxis dataKey="issue" tickFormatter={fmtDate} tick={{ fontSize: 11 }} padding={{ left: 16, right: 16 }} />
            <YAxis width={44} tick={{ fontSize: 11 }} unit={metric.unit === "%" ? "%" : undefined} domain={metric.domain ?? ["auto", "auto"]} />
            <Tooltip
              labelFormatter={(label) => `Issued ${fmtDate(String(label))}`}
              formatter={(value, _name, item) => {
                const row = item.payload as Row;
                const kind = row.was_future_at_fetch ? "forecast" : "observed";
                return [`${typeof value === "number" ? value.toFixed(metric.digits) : "–"} ${metric.unit} (${kind}, fetched ${fmtDateTime(row.fetched_at)} UTC)`];
              }}
            />
            <Line
              type="monotone"
              dataKey="value"
              name={metric.label}
              stroke={color}
              strokeWidth={2}
              connectNulls
              isAnimationActive={false}
              dot={(props) => <IssueDot {...props} color={color} />}
              activeDot={{ r: 6 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

interface DotProps {
  cx?: number;
  cy?: number;
  index?: number;
  payload?: Row;
  color: string;
}

// Filled dot: a genuine prediction. Hollow dot: the hour had already passed
// when that issue was fetched, so the value is Open-Meteo's observation.
function IssueDot({ cx, cy, index, payload, color }: DotProps) {
  if (cx === undefined || cy === undefined || payload?.value === null) return <g key={index} />;
  const observed = payload ? !payload.was_future_at_fetch : false;
  return (
    <circle
      key={index}
      cx={cx}
      cy={cy}
      r={index === 0 ? 6 : 4.5}
      fill={observed ? "white" : color}
      stroke={color}
      strokeWidth={2}
    />
  );
}
