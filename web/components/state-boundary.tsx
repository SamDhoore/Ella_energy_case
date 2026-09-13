"use client";

import type { ReactNode } from "react";
import { AlertCircle } from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import type { AsyncState } from "@/lib/use-api";
import { cn } from "@/lib/utils";

interface Props<T> {
  state: AsyncState<T>;
  skeleton: ReactNode;
  empty: { title: string; hint?: ReactNode };
  idle?: ReactNode;
  children: (data: T) => ReactNode;
}

/**
 * Renders exactly one of: loading skeleton, error banner (with retry), empty
 * notice, or the data. "We couldn't ask" and "there is nothing to show" must
 * look different (spec/01-dashboard.md §14).
 */
export function StateBoundary<T>({ state, skeleton, empty, idle, children }: Props<T>) {
  if (state.status === "idle") return <>{idle ?? null}</>;
  if (state.status === "loading") return <>{skeleton}</>;

  if (state.status === "error") {
    const title = state.error?.kind === "network" ? "Can't reach the API" : "The API reported a problem";
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertTitle>{title}</AlertTitle>
        <AlertDescription className="space-y-3">
          <p>
            {state.error?.message}
            {state.error?.code ? <span className="ml-2 font-mono text-xs opacity-70">{state.error.code}</span> : null}
          </p>
          <Button size="sm" variant="outline" onClick={state.refetch}>
            Retry
          </Button>
        </AlertDescription>
      </Alert>
    );
  }

  if (state.status === "empty") {
    return (
      <div className="rounded-md border border-dashed p-6 text-sm text-muted-foreground">
        <p className="font-medium text-foreground">{empty.title}</p>
        {empty.hint ? <div className="mt-1">{empty.hint}</div> : null}
        {state.error?.message ? <p className="mt-2 text-xs opacity-80">{state.error.message}</p> : null}
      </div>
    );
  }

  return <div className={cn(state.refreshing && "opacity-60 transition-opacity")}>{children(state.data as T)}</div>;
}
