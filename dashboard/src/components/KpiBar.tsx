import type { ReactNode } from "react";
import type { Connection } from "../useSimState";
import { clock, compact, duration } from "../lib/format";
import type { SimState } from "../types";
import { AnimatedNumber } from "./AnimatedNumber";

interface Props {
  state: SimState;
  connection: Connection;
}

function Kpi({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <div className="flex min-w-0 flex-col justify-center border-l border-slate-800 px-5 first:border-l-0">
      <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">{label}</div>
      <div className="truncate text-3xl font-bold tabular-nums leading-tight">{children}</div>
      {hint && <div className="truncate text-xs text-slate-500">{hint}</div>}
    </div>
  );
}

export function KpiBar({ state, connection }: Props) {
  const m = state.metrics;
  const improvement = m.plan_gain_pct;
  return (
    <header className="flex h-24 shrink-0 items-stretch border-b border-slate-800 bg-slate-950">
      <div className="flex flex-col justify-center px-5">
        <div className="text-xl font-black tracking-wide text-orange-400">PROMETHEUS</div>
        <div className="text-xs text-slate-400">Flood response · Nagpur</div>
        <div className="mt-1 w-fit rounded bg-amber-500 px-1.5 text-[11px] font-bold tracking-widest text-black">SIMULATED</div>
      </div>
      <div className="grid flex-1 grid-cols-5">
        <Kpi label="People at risk" hint={`rain ${state.rain_mm_hr} mm/hr`}>
          <span className="text-red-400">
            <AnimatedNumber value={m.people_at_risk} format={(n) => compact(Math.round(n))} />
          </span>
        </Kpi>
        <Kpi label="People reached" hint={`${m.served}/${m.incidents} SOS served`}>
          <span className="text-emerald-400">
            <AnimatedNumber value={m.people_reached} />
          </span>
        </Kpi>
        <Kpi label="Avg response" hint="SOS call → first responder on scene">
          {m.avg_response_s == null ? "—" : <AnimatedNumber value={m.avg_response_s} format={duration} />}
        </Kpi>
        <Kpi label="vs nearest-first" hint={`priority-weighted, over ${m.plans_compared} re-plans`}>
          {improvement == null ? (
            "—"
          ) : (
            <span className={improvement > 0 ? "text-emerald-400" : "text-slate-300"}>
              <AnimatedNumber value={improvement} format={(n) => `${n > 0 ? "+" : ""}${n.toFixed(1)}%`} />
            </span>
          )}
        </Kpi>
        <Kpi
          label="Sim clock"
          hint={`${state.clock.running ? "running" : "paused"} · ${state.clock.speed}× sim-s/s${connection !== "open" ? " · reconnecting…" : ""}`}
        >
          <span className={state.clock.running ? "text-sky-300" : "text-slate-400"}>{clock(state.time_s)}</span>
        </Kpi>
      </div>
    </header>
  );
}
