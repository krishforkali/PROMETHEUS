import type { Incident, VehicleType } from "../types";

export function clock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(Math.floor(s / 3600))}:${pad(Math.floor((s % 3600) / 60))}:${pad(s % 60)}`;
}

export function duration(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  const s = Math.max(0, Math.round(seconds));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
}

export function compact(n: number): string {
  return n >= 10_000 ? `${(n / 1000).toFixed(n >= 100_000 ? 0 : 1)}k` : n.toLocaleString("en-IN");
}

export function priority(inc: Pick<Incident, "severity" | "people">): number {
  return inc.severity * inc.people;
}

export type PriorityBand = "critical" | "high" | "medium" | "low";

export function priorityBand(p: number): PriorityBand {
  if (p >= 100) return "critical";
  if (p >= 40) return "high";
  if (p >= 15) return "medium";
  return "low";
}

export const BAND_COLOR: Record<PriorityBand, string> = {
  critical: "#ef4444",
  high: "#f97316",
  medium: "#eab308",
  low: "#38bdf8",
};

export const VEHICLE_COLOR: Record<VehicleType, string> = {
  ambulance: "#f8fafc",
  boat: "#22d3ee",
  drone: "#a78bfa",
  truck: "#fbbf24",
};

export const VEHICLE_ICON: Record<VehicleType, string> = {
  ambulance: "🚑",
  boat: "🚤",
  drone: "🛸",
  truck: "🚚",
};

/** Queue order: unserved first by priority (desc), then served most-recent first. */
export function queueOrder(incidents: Incident[]): Incident[] {
  return [...incidents].sort((a, b) => {
    const aDone = a.status === "served" ? 1 : 0;
    const bDone = b.status === "served" ? 1 : 0;
    if (aDone !== bDone) return aDone - bDone;
    if (aDone) return (b.served_s ?? 0) - (a.served_s ?? 0);
    return priority(b) - priority(a) || a.created_s - b.created_s || a.id.localeCompare(b.id);
  });
}

/** Map a 0..1 risk value onto a green -> amber -> red ramp. */
export function riskColor(risk: number): string {
  const r = Math.min(Math.max(risk, 0), 1);
  const stops: [number, [number, number, number]][] = [
    [0, [34, 197, 94]],
    [0.35, [234, 179, 8]],
    [0.7, [239, 68, 68]],
    [1, [153, 27, 27]],
  ];
  for (let i = 1; i < stops.length; i++) {
    const [p1, c1] = stops[i]!;
    const [p0, c0] = stops[i - 1]!;
    if (r <= p1) {
      const f = (r - p0) / (p1 - p0);
      const mix = c0.map((c, k) => Math.round(c + f * (c1[k]! - c)));
      return `rgb(${mix.join(",")})`;
    }
  }
  return "rgb(153,27,27)";
}
