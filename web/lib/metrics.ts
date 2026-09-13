// The three hourly metrics both chart panes show, and the shared colour ramp.

export type MetricKey = "temperature_2m" | "precipitation" | "precipitation_probability";

export interface Metric {
  key: MetricKey;
  label: string;
  unit: string;
  digits: number;
  domain?: [number, number];
}

export const METRICS: readonly Metric[] = [
  { key: "temperature_2m", label: "Temperature", unit: "°C", digits: 1 },
  { key: "precipitation", label: "Precipitation", unit: "mm", digits: 1 },
  { key: "precipitation_probability", label: "Precipitation probability", unit: "%", digits: 0, domain: [0, 100] },
];

// Latest issue is drawn first and boldest; older issues fade progressively.
export const PALETTE = [
  "#0f172a",
  "#2563eb",
  "#7c3aed",
  "#db2777",
  "#ea580c",
  "#ca8a04",
  "#16a34a",
  "#0891b2",
  "#64748b",
  "#a16207",
];
