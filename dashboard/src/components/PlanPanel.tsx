import { duration } from "../lib/format";
import type { SimState } from "../types";

export function PlanPanel({ state }: { state: SimState }) {
  const plan = state.plan;
  const labels = new Map(state.vehicles.map((v) => [v.id, v.label]));
  if (!plan) return <section className="p-3 text-slate-500">No plan yet.</section>;
  const m = plan.metrics;
  const b = plan.baseline;

  return (
    <section className="flex min-h-0 flex-col">
      <h2 className="panel-title">
        Dispatch plan v{plan.version} <span className="text-slate-500">· {plan.solver} · after: {plan.reason}</span>
      </h2>
      <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_16rem] gap-3 p-2">
        <ul className="min-h-0 space-y-1 overflow-y-auto text-sm">
          {plan.assignments.length === 0 && <li className="text-slate-500">Nothing to dispatch.</li>}
          {plan.assignments.map((a) => (
            <li key={`${a.vehicle}-${a.incident}`} className="flex gap-2 rounded bg-slate-900 px-2 py-1">
              <span className="w-28 shrink-0 font-semibold">{labels.get(a.vehicle) ?? a.vehicle}</span>
              <span>→ {a.incident}</span>
              <span className="ml-auto text-slate-400">ETA {duration(a.eta_s - state.time_s)}</span>
            </li>
          ))}
          {plan.dropped.length > 0 && <li className="px-2 text-xs text-red-300">Not dispatched: {plan.dropped.join(", ")}</li>}
        </ul>
        <table className="h-fit text-sm">
          <thead>
            <tr className="text-xs text-slate-500">
              <th />
              <th className="text-right font-normal">Optimised</th>
              <th className="text-right font-normal">Nearest-first</th>
            </tr>
          </thead>
          <tbody className="tabular-nums">
            <tr>
              <td className="text-slate-400">Served</td>
              <td className="text-right">{m.served}</td>
              <td className="text-right text-slate-400">{b.served}</td>
            </tr>
            <tr>
              <td className="text-slate-400">People</td>
              <td className="text-right">{m.people_reached}</td>
              <td className="text-right text-slate-400">{b.people_reached}</td>
            </tr>
            <tr>
              <td className="text-slate-400">Avg ETA</td>
              <td className="text-right">{duration(m.avg_response_s)}</td>
              <td className="text-right text-slate-400">{duration(b.avg_response_s)}</td>
            </tr>
            <tr>
              <td className="text-slate-400">Gain</td>
              <td className="text-right font-bold text-emerald-400" colSpan={2}>
                {plan.improvement_pct.cost == null ? "—" : `${plan.improvement_pct.cost.toFixed(1)}%`}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  );
}
