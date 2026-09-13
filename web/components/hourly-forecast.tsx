"use client";

import { useMemo } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { StateBoundary } from "@/components/state-boundary";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { fmtDate, fmtDateTime, fmtTick } from "@/lib/format";
import { METRICS, PALETTE, type Metric } from "@/lib/metrics";
import type { RevisionsResponse } from "@/lib/types";
import { useApi } from "@/lib/use-api";

interface Props {
  city: string;
  horizonHours: number;
}

/** Pane (i): the coming hours, one line per forecast issue. */
export function HourlyForecast({ city, horizonHours }: Props) {
  const state = useApi(
    (signal) => api.revisions(city, horizonHours, signal),
    [city, horizonHours],
    (d) => d.series.length === 0,
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>Hourly forecast</CardTitle>
        <CardDescription>
          Latest issue plus how earlier issues predicted the same hours. One line per forecast date; times in UTC.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <StateBoundary
          state={state}
          skeleton={
            <div className="space-y-6">
              {METRICS.map((m) => (
                <Skeleton key={m.key} className="h-56 w-full" />
              ))}
            </div>
          }
          empty={{
            title: `No forecast data yet for ${city}.`,
            hint: "Check the ingestion health panel: the first ingest may still be running or may have failed.",
          }}
        >
          {(data) => (
            <>
              <p className="text-xs text-muted-foreground">
                Window {fmtDateTime(data.window_start)} → {fmtDateTime(data.window_end)} UTC · {data.series.length}{" "}
                {data.series.length === 1 ? "issue" : "issues"} shown
                {data.series.length === 1 ? " (revision lines appear once a second daily ingest has run)" : ""}
              </p>
              {METRICS.map((metric) => (
                <MetricChart key={metric.key} data={data} metric={metric} />
              ))}
            </>
          )}
        </StateBoundary>
      </CardContent>
    </Card>
  );
}

type Row = { t: string } & Record<string, number | string | null>;

function MetricChart({ data, metric }: { data: RevisionsResponse; metric: Metric }) {
  const rows = useMemo(() => buildRows(data, metric.key), [data, metric.key]);
  return (
    <div>
      <h3 className="mb-1 text-sm font-medium">
        {metric.label} <span className="text-muted-foreground">({metric.unit})</span>
      </h3>
      <div className="h-56 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
            <XAxis dataKey="t" tickFormatter={fmtTick} minTickGap={28} tick={{ fontSize: 11 }} />
            <YAxis width={44} tick={{ fontSize: 11 }} domain={metric.domain ?? ["auto", "auto"]} />
            <Tooltip
              labelFormatter={(label) => `${fmtDateTime(String(label))} UTC`}
              formatter={(value) => [typeof value === "number" ? `${value.toFixed(metric.digits)} ${metric.unit}` : "–"]}
            />
            <Legend wrapperStyle={{ fontSize: 11 }} />
            {data.series.map((s, i) => (
              <Line
                key={s.forecast_run_id}
                type="monotone"
                dataKey={s.date_forecast_made}
                name={i === 0 ? `${fmtDate(s.date_forecast_made)} (latest)` : fmtDate(s.date_forecast_made)}
                stroke={PALETTE[i % PALETTE.length]}
                strokeWidth={i === 0 ? 2.5 : 1.5}
                strokeOpacity={i === 0 ? 1 : Math.max(0.35, 0.8 - i * 0.08)}
                dot={false}
                connectNulls
                isAnimationActive={false}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function buildRows(data: RevisionsResponse, key: Metric["key"]): Row[] {
  const rows: Row[] = data.target_times.map((t) => ({ t }));
  const index = new Map(data.target_times.map((t, i) => [t, i]));
  for (const series of data.series) {
    for (const point of series.points) {
      const i = index.get(point.target_time);
      if (i !== undefined) rows[i][series.date_forecast_made] = point[key];
    }
  }
  return rows;
}
