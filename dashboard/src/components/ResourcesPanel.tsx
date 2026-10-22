import { VEHICLE_COLOR, VEHICLE_ICON } from "../lib/format";
import type { SimState, VehicleStatus, VehicleType } from "../types";

const STATUS_LABEL: Record<VehicleStatus, string> = {
  idle: "idle",
  en_route: "en route",
  transporting: "to hospital",
  lost: "LOST",
};

const STATUS_STYLE: Record<VehicleStatus, string> = {
  idle: "text-slate-400",
  en_route: "text-amber-300",
  transporting: "text-sky-300",
  lost: "text-red-500 line-through",
};

const TYPES: VehicleType[] = ["ambulance", "boat", "drone", "truck"];

export function ResourcesPanel({ state }: { state: SimState }) {
  const hospitals = new Map(state.hospitals.map((h) => [h.id, h.name]));
  return (
    <section className="flex min-h-0 flex-col">
      <h2 className="panel-title">Resources</h2>
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-2">
        {TYPES.map((type) => {
          const fleet = state.vehicles.filter((v) => v.type === type);
          const active = fleet.filter((v) => v.status !== "lost").length;
          return (
            <div key={type}>
              <div className="mb-1 flex items-center gap-2 text-sm font-semibold" style={{ color: VEHICLE_COLOR[type] }}>
                <span>{VEHICLE_ICON[type]}</span>
                <span className="capitalize">{type}s</span> <span className="text-xs font-normal text-slate-500">{active}/{fleet.length} available</span>
              </div>
              <ul className="space-y-0.5">
                {fleet.map((v) => (
                  <li key={v.id} className="flex items-center gap-2 rounded bg-slate-900 px-2 py-1 text-sm">
                    <span className="w-24 shrink-0">{v.label}</span>
                    <span className={`shrink-0 text-xs font-semibold ${STATUS_STYLE[v.status]}`}>{STATUS_LABEL[v.status]}</span>
                    <span className="ml-auto truncate text-xs text-slate-400">
                      {v.target ? (v.target.kind === "hospital" ? `→ ${hospitals.get(v.target.id) ?? v.target.id}` : `→ ${v.target.id}`) : ""}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>
    </section>
  );
}
