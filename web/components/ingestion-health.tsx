"use client";

import { AlertTriangle, CheckCircle2 } from "lucide-react";

import { StateBoundary } from "@/components/state-boundary";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { fmtAgo, fmtDateTime } from "@/lib/format";
import type { CityHealth } from "@/lib/types";
import { useApi } from "@/lib/use-api";

export function IngestionHealth({ city }: { city: string }) {
  const state = useApi(
    (signal) => api.health(city, signal),
    [city],
    (d) => d.cities.length === 0 || d.cities[0].last_attempt === null,
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>Ingestion health</CardTitle>
        <CardDescription>From the ingest_run log. Re-fetched when you change city or reload.</CardDescription>
      </CardHeader>
      <CardContent>
        <StateBoundary
          state={state}
          skeleton={<Skeleton className="h-24 w-full" />}
          empty={{
            title: `No ingestion recorded yet for ${city}.`,
            hint: "On a fresh start the first ingest runs right after the database is ready; reload in a moment.",
          }}
        >
          {(data) => <HealthBody health={data.cities[0]} />}
        </StateBoundary>
      </CardContent>
    </Card>
  );
}

function HealthBody({ health }: { health: CityHealth }) {
  const { last_attempt: attempt, last_success: success } = health;
  return (
    <div className="space-y-4">
      {health.healthy ? (
        <Alert>
          <CheckCircle2 className="h-4 w-4" />
          <AlertTitle>Latest ingest succeeded</AlertTitle>
          <AlertDescription>
            {attempt ? (
              <>
                {fmtDateTime(attempt.finished_at)} UTC ({fmtAgo(attempt.finished_at)}), {attempt.rows_written} rows written.
              </>
            ) : null}
          </AlertDescription>
        </Alert>
      ) : (
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>
            Most recent ingest attempt failed{attempt ? <>: <Badge variant="destructive" className="ml-1 align-middle">{attempt.status}</Badge></> : null}
          </AlertTitle>
          <AlertDescription className="space-y-1">
            {attempt ? (
              <>
                <p>
                  {fmtDateTime(attempt.started_at)} UTC ({fmtAgo(attempt.started_at)})
                </p>
                {attempt.error_detail ? <p className="font-mono text-xs break-words">{attempt.error_detail}</p> : null}
              </>
            ) : null}
            <p>
              {success
                ? `Data shown comes from the last successful ingest at ${fmtDateTime(success.finished_at)} UTC.`
                : "There has never been a successful ingest for this city, so no forecast data exists yet."}
            </p>
          </AlertDescription>
        </Alert>
      )}

      <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
        <div className="rounded-md border p-3">
          <dt className="text-xs uppercase tracking-wide text-muted-foreground">Last successful ingest</dt>
          <dd className="mt-1">
            {success ? (
              <>
                {fmtDateTime(success.finished_at)} UTC
                <span className="ml-2 text-muted-foreground">{success.rows_written} rows</span>
              </>
            ) : (
              "never"
            )}
          </dd>
        </div>
        <div className="rounded-md border p-3">
          <dt className="text-xs uppercase tracking-wide text-muted-foreground">Last attempt</dt>
          <dd className="mt-1">
            {attempt ? (
              <>
                {fmtDateTime(attempt.started_at)} UTC
                <Badge variant={attempt.status === "SUCCESS" ? "success" : "destructive"} className="ml-2">
                  {attempt.status}
                </Badge>
              </>
            ) : (
              "never"
            )}
          </dd>
        </div>
      </dl>
    </div>
  );
}
