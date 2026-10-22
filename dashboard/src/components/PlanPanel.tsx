import { useEffect, useState } from "react";
import { api } from "../api";
import { duration } from "../lib/format";
import { changeLines, whyLines } from "../lib/why";
import type { Assignment, Plan, SimState } from "../types";

interface Props {
  state: SimState;
  onError: (msg: string) => void;
}

interface Open {
  assignment: Assignment;
  x: number;
  y: number;
}

export function PlanPanel({ state, onError }: Props) {
  const [why, setWhy] = useState<Open | null>(null);
  const labels = new Map(state.vehicles.map((v) => [v.id, v.label]));
  const label = (id: string) => labels.get(id) ?? id;
  const proposal = state.proposal;
  const plan: Plan | null = proposal ?? state.plan;
  const run = (p: Promise<unknown>) => p.catch((e: unknown) => onError(e instanceof Error ? e.message : String(e)));

  useEffect(() => {
    if (!why) return;
    const close = () => setWhy(null);
    window.addEventListener("click", close);
    return () => window.removeEventListener("click", close);
  }, [why]);

  return (
    <section className="flex min-h-0 flex-col">
      <h2 className="panel-title flex items-center gap-2">
        <span>
          Dispatch plan {plan ? `v${plan.version}` : ""}
          {plan && <span className="font-normal normal-case text-slate-500"> · {plan.solver} · after {plan.reason}</span>}
        </span>
        <label className="ml-auto flex items-center gap-1.5 text-xs font-semibold normal-case tracking-normal text-slate-300">
          <input type="checkbox" checked={state.auto_approve} onChange={(e) => run(api.autoApprove(e.target.checked))} />
          Auto-approve
        </label>
      </h2>

      {proposal && (
        <div className="flex shrink-0 items-start gap-3 border-b border-amber-700 bg-amber-950/70 px-3 py-2">
          <div className="min-w-0 flex-1">
            <div className="font-bold text-amber-300">
              New plan proposed <span className="font-normal text-amber-200/80">· clock held until approved</span>
            </div>
            <ul className="text-sm text-amber-100">
              {changeLines(proposal.changes, label).map((l) => (
                <li key={l} className="truncate">
                  {l}
                </li>
              ))}
            </ul>
          </div>
          <button className="btn shrink-0 bg-emerald-600 px-4 py-2 text-base" onClick={() => run(api.approve())}>
            ✓ Approve
          </button>
        </div>
      )}

      {!plan ? (
        <div className="p-3 text-slate-500">No plan yet.</div>
      ) : (
        <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_15rem] gap-3 p-2">
          <ul className="min-h-0 space-y-1 overflow-y-auto text-sm">
            {plan.assignments.length === 0 && <li className="text-slate-500">Nothing to dispatch.</li>}
            {plan.assignments.map((a) => {
              const served = state.incidents.find((i) => i.id === a.incident)?.status === "served";
              return (
                <li key={`${a.vehicle}-${a.incident}`} className={`flex items-center gap-2 rounded bg-slate-900 px-2 py-1 ${served ? "opacity-40" : ""}`}>
                  <span className="w-28 shrink-0 font-semibold">{label(a.vehicle)}</span>
                  <span>→ {a.incident}</span>
                  <span className="text-xs text-slate-500">P{a.why.priority}</span>
                  <span className="ml-auto text-slate-400">{served ? "on scene" : `ETA ${duration(a.eta_s - state.time_s)}`}</span>
                  <button
                    className="rounded bg-slate-700 px-2 text-xs font-semibold hover:bg-slate-600"
                    onClick={(e) => {
                      e.stopPropagation();
                      const r = e.currentTarget.getBoundingClientRect();
                      setWhy({ assignment: a, x: r.right, y: r.top });
                    }}
                  >
                    Why?
                  </button>
                </li>
              );
            })}
            {plan.dropped.length > 0 && <li className="px-2 text-xs text-red-300">Not dispatched: {plan.dropped.join(", ")}</li>}
          </ul>
          <Comparison plan={plan} />
        </div>
      )}

      {why && (
        <div
          className="fixed z-50 w-[26rem] rounded-lg border border-slate-600 bg-slate-900 p-3 text-sm shadow-2xl"
          style={{ left: Math.min(why.x + 8, window.innerWidth - 430), bottom: window.innerHeight - why.y + 8 }}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="mb-1 font-bold">
            Why {label(why.assignment.vehicle)} → {why.assignment.incident}?
          </div>
          <ul className="list-disc space-y-1 pl-4 text-slate-300">
            {whyLines(why.assignment, state.time_s, label).map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}

function Comparison({ plan }: { plan: Plan }) {
  const m = plan.metrics;
  const b = plan.baseline;
  const rows: [string, string | number, string | number][] = [
    ["Served", m.served, b.served],
    ["People", m.people_reached, b.people_reached],
    ["Avg ETA", duration(m.avg_response_s), duration(b.avg_response_s)],
  ];
  return (
    <table className="h-fit text-sm">
      <thead>
        <tr className="text-xs text-slate-500">
          <th />
          <th className="text-right font-normal">Optimised</th>
          <th className="text-right font-normal">Nearest-first</th>
        </tr>
      </thead>
      <tbody className="tabular-nums">
        {rows.map(([k, a, c]) => (
          <tr key={k}>
            <td className="text-slate-400">{k}</td>
            <td className="text-right">{a}</td>
            <td className="text-right text-slate-400">{c}</td>
          </tr>
        ))}
        <tr>
          <td className="text-slate-400">Gain</td>
          <td className="text-right font-bold text-emerald-400" colSpan={2}>
            {plan.improvement_pct.cost == null ? "—" : `${plan.improvement_pct.cost.toFixed(1)}%`}
          </td>
        </tr>
      </tbody>
    </table>
  );
}
