"use client";

import { StateBoundary } from "@/components/state-boundary";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { fmtDate, fmtDateTime, fmtNum } from "@/lib/format";
import { useApi } from "@/lib/use-api";
import { cn } from "@/lib/utils";

interface Props {
  city: string;
  forecastDate: string | null; // null = latest
  onForecastDateChange: (value: string | null) => void;
}

export function DailyMatrix({ city, forecastDate, onForecastDateChange }: Props) {
  // Dropdown options come from what the database actually holds.
  const dates = useApi((signal) => api.dates(city, signal), [city], (d) => d.dates.length === 0);
  const selected = forecastDate ?? dates.data?.dates[0] ?? null;
  const daily = useApi(
    selected ? (signal) => api.daily(city, selected, signal) : null,
    [city, selected],
    (d) => d.points.length === 0,
  );

  return (
    <Card>
      <CardHeader className="gap-3 sm:flex-row sm:items-start sm:justify-between sm:space-y-0">
        <div className="space-y-1.5">
          <CardTitle>Daily matrix</CardTitle>
          <CardDescription>Daily maxima per UTC day for one forecast issue. Visibility is the day&apos;s lowest hourly reading.</CardDescription>
        </div>
        <Select
          value={selected ?? ""}
          onValueChange={(v) => onForecastDateChange(v || null)}
          disabled={dates.status !== "ok"}
        >
          <SelectTrigger className="w-full sm:w-56" aria-label="Forecast issue date">
            <SelectValue placeholder="Forecast issue date" />
          </SelectTrigger>
          <SelectContent>
            {(dates.data?.dates ?? []).map((d, i) => (
              <SelectItem key={d} value={d}>
                {fmtDate(d)}
                {i === 0 ? " (latest)" : ""}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </CardHeader>
      <CardContent>
        <StateBoundary
          state={dates}
          skeleton={<Skeleton className="h-64 w-full" />}
          empty={{ title: `No forecast issues stored yet for ${city}.`, hint: "The daily matrix appears after the first successful ingest." }}
        >
          {() => (
            <StateBoundary
              state={daily}
              skeleton={<Skeleton className="h-64 w-full" />}
              empty={{ title: "This forecast issue has no daily values." }}
            >
              {(data) => (
                <>
                  <p className="mb-3 text-xs text-muted-foreground">
                    Issue of {fmtDate(data.run.date_forecast_made)}, fetched {fmtDateTime(data.run.fetched_at)} UTC. Days before the
                    issue date are past observations included by the ingest window.
                  </p>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Day (UTC)</TableHead>
                        <TableHead className="text-right">Max temp</TableHead>
                        <TableHead className="text-right">UV max</TableHead>
                        <TableHead className="text-right">Max gusts</TableHead>
                        <TableHead className="text-right">Sunshine</TableHead>
                        <TableHead className="text-right">Min visibility</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {data.points.map((p) => {
                        const past = p.target_date < data.run.date_forecast_made;
                        return (
                          <TableRow key={p.target_date} className={cn(past && "text-muted-foreground")}>
                            <TableCell className="font-medium">
                              {fmtDate(p.target_date)}
                              {past ? <Badge variant="outline" className="ml-2 font-normal">past</Badge> : null}
                              {p.target_date === data.run.date_forecast_made ? <Badge variant="secondary" className="ml-2 font-normal">issue day</Badge> : null}
                            </TableCell>
                            <TableCell className="text-right">{fmtNum(p.temperature_2m_max, 1, " °C")}</TableCell>
                            <TableCell className="text-right">{fmtNum(p.uv_index_max, 1)}</TableCell>
                            <TableCell className="text-right">{fmtNum(p.wind_gusts_10m_max, 0, " km/h")}</TableCell>
                            <TableCell className="text-right">{fmtNum(p.sunshine_duration === null ? null : p.sunshine_duration / 3600, 1, " h")}</TableCell>
                            <TableCell className="text-right">{fmtNum(p.visibility_min === null ? null : p.visibility_min / 1000, 1, " km")}</TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </>
              )}
            </StateBoundary>
          )}
        </StateBoundary>
      </CardContent>
    </Card>
  );
}
