// Every value from the API is UTC; the dashboard displays UTC explicitly
// rather than silently converting to the viewer's zone.
const UTC = "UTC";

export function fmtDateTime(iso: string): string {
  return new Date(iso).toLocaleString("en-GB", {
    timeZone: UTC,
    weekday: "short",
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function fmtTick(iso: string): string {
  const d = new Date(iso);
  const hour = d.toLocaleString("en-GB", { timeZone: UTC, hour: "2-digit", minute: "2-digit" });
  return hour === "00:00" ? d.toLocaleString("en-GB", { timeZone: UTC, weekday: "short", day: "2-digit" }) : hour;
}

export function fmtDate(isoDate: string): string {
  return new Date(`${isoDate}T00:00:00Z`).toLocaleDateString("en-GB", {
    timeZone: UTC,
    weekday: "short",
    day: "2-digit",
    month: "short",
  });
}

export function fmtNum(value: number | null | undefined, digits = 1, unit = ""): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "–";
  return `${value.toFixed(digits)}${unit}`;
}

export function fmtAgo(iso: string, now = Date.now()): string {
  const seconds = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} h ago`;
  return `${Math.round(hours / 24)} d ago`;
}
