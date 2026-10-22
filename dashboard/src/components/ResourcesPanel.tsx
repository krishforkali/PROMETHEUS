import { VEHICLE_COLOR, VEHICLE_ICON } from "../lib/format";
import type { SimState, VehicleStatus } from "../types";

const STATUS_LABEL: Record<VehicleStatus, string> = {
  idle: "idle",
  en_route: "en route",
  transporting: "to hospital",
  lost: "LOST",
};

const STATUS_STYLE: Record<VehicleStatus, string> = {
  idle: "text-slate-500",
  en_route: "text-amber-300",
  transporting: "text-sky-300",
  lost: "text-red-500",
};

export function ResourcesPanel({ state }: { state: SimState }) {
  const lost = state.vehicles.filter((v) => v.status === "lost").length;
  return (
    <>
      <section>
        <h2 className="panel-title">
          Fleet{" "}
          <span className="font-normal normal-case text-slate-500">
            · {state.vehicles.length - lost}/{state.vehicles.length} available
          </span>
        </h2>
        <ul className="space-y-0.5 p-2 text-sm">
          {state.vehicles.map((v) => (
            <li
              key={v.id}
              className={`flex items-center gap-1.5 rounded border-l-4 bg-slate-900 px-1.5 py-0.5 ${v.status === "lost" ? "opacity-50" : ""}`}
              style={{ borderColor: VEHICLE_COLOR[v.type] }}
            >
              <span>{VEHICLE_ICON[v.type]}</span>
              <span className={`w-24 shrink-0 ${v.status === "lost" ? "line-through" : ""}`}>{v.label}</span>
              <span className={`shrink-0 text-xs font-semibold ${STATUS_STYLE[v.status]}`}>{STATUS_LABEL[v.status]}</span>
              <span className="ml-auto truncate text-xs text-slate-500">{v.target ? `→ ${v.target.kind === "hospital" ? "hospital" : v.target.id}` : ""}</span>
            </li>
          ))}
        </ul>
      </section>
      <section>
        <h2 className="panel-title">
          Hospital beds <span className="font-normal normal-case text-slate-500">· simulated capacity</span>
        </h2>
        <ul className="space-y-1.5 p-2 text-sm">
          {state.hospitals.map((h) => {
            const frac = h.beds_available / Math.max(1, h.capacity.beds_total);
            const tone = frac < 0.15 ? "bg-red-500" : frac < 0.35 ? "bg-amber-500" : "bg-emerald-500";
            return (
              <li key={h.id}>
                <div className="flex justify-between gap-2">
                  <span className="truncate">{h.name}</span>
                  <span className="shrink-0 tabular-nums text-slate-300">
                    <b>{h.beds_available}</b>
                    <span className="text-slate-500">/{h.capacity.beds_total}</span>
                  </span>
                </div>
                <div className="mt-0.5 h-2 rounded bg-slate-800">
                  <div className={`h-2 rounded transition-all duration-700 ${tone}`} style={{ width: `${frac * 100}%` }} />
                </div>
              </li>
            );
          })}
        </ul>
      </section>
    </>
  );
}
