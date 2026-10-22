import type { Assignment, PlanChanges } from "../types";
import { duration } from "./format";

type Labels = (id: string) => string;

function distance(m: number, mode: Assignment["why"]["mode"]): string {
  const km = m >= 1000 ? `${(m / 1000).toFixed(1)} km` : `${m} m`;
  return mode === "road" ? `${km} by road` : mode === "air" ? `${km} straight-line flight` : `${km} across water`;
}

/** Human-readable lines for the "Why?" popover. */
export function whyLines(a: Assignment, now: number, label: Labels): string[] {
  const w = a.why;
  const lines = [
    `Priority ${w.priority} (severity × people): #${w.rank} of ${w.of} calls in this plan.`,
    `${w.rule}.`,
    `${distance(w.distance_m, w.mode)}, about ${duration(w.travel_s)}${w.stop > 1 ? ` as stop ${w.stop} on its route` : ""}.`,
  ];
  const n = w.nearest;
  if (n.vehicle === a.vehicle) {
    lines.push("It is the nearest suitable vehicle.");
  } else if (n.busy_with.length) {
    lines.push(
      `Nearest suitable was ${label(n.vehicle)} (${duration(n.travel_s)} away), but the plan needs it for ${n.busy_with.join(", ")}.`,
    );
  } else {
    lines.push(
      `Nearest suitable was ${label(n.vehicle)} (${duration(n.travel_s)} away); keeping it free gives a lower total priority-weighted delay.`,
    );
  }
  lines.push(
    w.baseline
      ? w.baseline.vehicle === a.vehicle
        ? "Nearest-first would make the same choice."
        : `Nearest-first would send ${label(w.baseline.vehicle)} (ETA ${duration(w.baseline.eta_s - now)}).`
      : "Nearest-first would leave this call unserved.",
  );
  if (w.hospital) lines.push(`Then to ${w.hospital.name} (${w.hospital.beds_free} beds free).`);
  return lines;
}

/** One-line summaries of what a re-plan changes. */
export function changeLines(c: PlanChanges, label: Labels): string[] {
  const lines: string[] = [];
  if (c.added.length) lines.push(`${c.added.length} newly assigned: ${c.added.join(", ")}`);
  for (const r of c.reassigned) lines.push(`${r.incident}: ${label(r.from)} → ${label(r.to)}`);
  if (c.unassigned.length) lines.push(`No vehicle for: ${c.unassigned.join(", ")}`);
  if (!lines.length) lines.push(`No changes to ${c.unchanged} existing assignments`);
  return lines;
}
