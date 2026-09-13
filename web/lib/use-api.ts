"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError } from "./api";

export type Status = "idle" | "loading" | "ok" | "empty" | "error";

export interface AsyncState<T> {
  status: Status;
  data: T | null;
  error: ApiError | null;
  refreshing: boolean; // a refetch is in flight while previous data stays on screen
  refetch: () => void;
}

type Fetcher<T> = (signal: AbortSignal) => Promise<T>;

/**
 * Minimal request-state hook. Distinguishes the three states every view must
 * render (spec/01-dashboard.md §14): loading, empty (200 with nothing to show
 * or a 404 "valid request, no data"), and error (network failure or 5xx).
 */
export function useApi<T>(
  fetcher: Fetcher<T> | null,
  deps: readonly unknown[],
  isEmpty: (data: T) => boolean = () => false,
): AsyncState<T> {
  const [tick, setTick] = useState(0);
  const [state, setState] = useState<Omit<AsyncState<T>, "refetch">>({
    status: fetcher ? "loading" : "idle",
    data: null,
    error: null,
    refreshing: false,
  });
  const refetch = useCallback(() => setTick((t) => t + 1), []);

  useEffect(() => {
    if (!fetcher) {
      setState({ status: "idle", data: null, error: null, refreshing: false });
      return;
    }
    const controller = new AbortController();
    setState((prev) =>
      prev.data !== null
        ? { ...prev, refreshing: true, error: null }
        : { status: "loading", data: null, error: null, refreshing: false },
    );
    fetcher(controller.signal)
      .then((data) => {
        if (controller.signal.aborted) return;
        const empty = isEmpty(data);
        setState({ status: empty ? "empty" : "ok", data: empty ? null : data, error: null, refreshing: false });
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        const apiErr = err instanceof ApiError ? err : new ApiError("network", null, "UNKNOWN", String(err));
        setState({
          status: apiErr.kind === "not_found" ? "empty" : "error",
          data: null,
          error: apiErr,
          refreshing: false,
        });
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);

  return { ...state, refetch };
}
