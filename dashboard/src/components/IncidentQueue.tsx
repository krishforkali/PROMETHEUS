import { BAND_COLOR, duration, priority, priorityBand, queueOrder } from "../lib/format";
import type { IncidentSource, SimState } from "../types";

const SOURCE_STYLE: Record<IncidentSource, string> = {
  app: "bg-sky-500/20 text-sky-300",
  ivr: "bg-violet-500/20 text-violet-300",
  sms: "bg-emerald-500/20 text-emerald-300",
  dashboard: "bg-slate-500/30 text-slate-200",
};

const STATUS_STYLE = {
  open: "text-red-300",
  assigned: "text-amber-300",
  served: "text-emerald-400",
} as const;

export function IncidentQueue({ state }: { state: SimState }) {
  const labels = new Map(state.vehicles.map((v) => [v.id, v.label]));
  const incidents = queueOrder(state.incidents);
  const open = incidents.filter((i) => i.status !== "served").length;

  return (
    <section className="flex min-h-0 flex-col">
      <h2 className="panel-title">
        Incident queue <span className="text-slate-500">· {open} open</span>
      </h2>
      <ul className="min-h-0 flex-1 space-y-1.5 overflow-y-auto p-2">
        {incidents.length === 0 && <li className="p-3 text-sm text-slate-500">No SOS calls yet.</li>}
        {incidents.map((i) => {
          const p = priority(i);
          const done = i.status === "served";
          return (
            <li
              key={i.id}
              className={`rounded-md border-l-4 bg-slate-900 px-2.5 py-1.5 ${done ? "opacity-45" : ""}`}
              style={{ borderColor: done ? "#334155" : BAND_COLOR[priorityBand(p)] }}
            >
              <div className="flex items-center gap-2">
                <span className="font-mono text-sm font-semibold">{i.id}</span>
                <span className={`rounded px-1.5 text-[11px] font-semibold uppercase ${SOURCE_STYLE[i.source]}`}>{i.source}</span>
                <span className="text-xs text-slate-400">{i.zone}</span>
                <span className="ml-auto text-sm font-bold tabular-nums">P{p}</span>
              </div>
              <div className="flex items-center gap-2 text-xs text-slate-300">
                <span>
                  {i.people} people · sev {i.severity} · {i.kind}
                </span>
                <span className={`ml-auto font-semibold ${STATUS_STYLE[i.status]}`}>
                  {i.status === "assigned" && i.assigned_to
                    ? `${labels.get(i.assigned_to) ?? i.assigned_to} · ETA ${duration((i.eta_s ?? 0) - state.time_s)}`
                    : i.status === "served"
                      ? `reached by ${labels.get(i.served_by ?? "") ?? i.served_by}`
                      : "unassigned"}
                </span>
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
