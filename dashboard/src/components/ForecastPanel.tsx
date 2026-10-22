import { riskColor } from "../lib/format";
import type { SimState } from "../types";

export function ForecastPanel({ state }: { state: SimState }) {
  const cut = state.zones.filter((z) => z.cut_off).map((z) => z.id);
  const total = state.zones.reduce(
    (acc, z) => ({ low: acc.low + z.casualties.low, expected: acc.expected + z.casualties.expected, high: acc.high + z.casualties.high }),
    { low: 0, expected: 0, high: 0 },
  );
  const zones = [...state.zones].sort((a, b) => b.risk - a.risk || a.id.localeCompare(b.id));

  return (
    <section>
      <h2 className="panel-title">
        Forecast <span className="font-normal normal-case text-slate-500">· simulated, formula-based</span>
      </h2>
      <div className="space-y-2 p-2 text-sm">
        <div className="flex items-baseline justify-between rounded bg-slate-900 px-2 py-1.5">
          <span className="text-slate-400">Casualty estimate</span>
          <span className="tabular-nums">
            <b className="text-lg text-red-300">{total.expected}</b>{" "}
            <span className="text-slate-400">
              ({total.low}–{total.high})
            </span>
          </span>
        </div>
        {cut.length > 0 && (
          <div className="rounded border border-red-700 bg-red-950/60 px-2 py-1 font-semibold text-red-200">
            Cut off from all hospitals: {cut.join(", ")}
          </div>
        )}
        <table className="w-full tabular-nums">
          <thead>
            <tr className="text-left text-xs text-slate-500">
              <th className="font-normal">Zone</th>
              <th className="font-normal">Risk</th>
              <th className="text-right font-normal">Casualties</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {zones.map((z) => (
              <tr key={z.id} className="h-6">
                <td className="font-semibold">{z.id}</td>
                <td className="w-24 pr-2">
                  <div className="h-2 rounded bg-slate-800">
                    <div className="h-2 rounded transition-all duration-500" style={{ width: `${Math.round(z.risk * 100)}%`, background: riskColor(z.risk) }} />
                  </div>
                </td>
                <td className="text-right">
                  {z.casualties.expected} <span className="text-xs text-slate-500">({z.casualties.low}–{z.casualties.high})</span>
                </td>
                <td className="pl-2 text-right text-[11px] font-bold">
                  {z.cut_off && <span className="rounded bg-red-600 px-1">CUT</span>}
                  {z.flooded && <span className="ml-1 rounded bg-blue-600 px-1">FLOOD</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <div>
          <div className="mb-1 text-xs uppercase tracking-wider text-slate-500">Failure points</div>
          <ul className="space-y-0.5">
            {state.failure_points.map((f) => (
              <li key={f.id} className="flex items-center gap-2">
                <span className={`h-2.5 w-2.5 rotate-45 ${f.failed ? "bg-red-500" : "bg-amber-500"}`} />
                <span className={f.failed ? "font-semibold text-red-300" : ""}>{f.label}</span>
                <span className="truncate text-xs text-slate-500">{f.zone}</span>
                <span className={`ml-auto text-xs font-semibold ${f.failed ? "text-red-400" : "text-slate-400"}`}>
                  {f.failed ? "FAILED" : `risk ${Math.round(f.risk * 100)}%`}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
