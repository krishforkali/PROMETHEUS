import { clock } from "../lib/format";
import type { LogEntry, SimState } from "../types";

const TYPE_STYLE: Record<string, string> = {
  fail: "text-red-400",
  block_road: "text-red-400",
  vehicle_lost: "text-red-400",
  remove_vehicle: "text-red-400",
  sos_wave: "text-orange-300",
  add_sos: "text-orange-300",
  add_sos_wave: "text-orange-300",
  rain: "text-sky-300",
  served: "text-emerald-300",
  hospital: "text-teal-300",
  proposal: "font-semibold text-amber-300",
  approved: "text-emerald-400",
};

export function EventFeed({ state }: { state: SimState }) {
  const entries: LogEntry[] = [...state.log].reverse();
  return (
    <section className="flex min-h-0 flex-col">
      <h2 className="panel-title">Event feed</h2>
      <ul className="min-h-0 flex-1 space-y-0.5 overflow-y-auto p-2 font-mono text-[13px]">
        {entries.map((e, k) => (
          <li key={`${e.t}-${k}-${e.message}`} className="flex gap-2">
            <span className="shrink-0 text-slate-500">{clock(e.t)}</span>
            <span className={TYPE_STYLE[e.type] ?? "text-slate-300"}>{e.message}</span>
            {e.source === "manual" && <span className="text-xs text-slate-500">(operator)</span>}
          </li>
        ))}
      </ul>
    </section>
  );
}
