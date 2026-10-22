import { useState } from "react";
import { api } from "../api";
import type { SimEvent, SimState } from "../types";

// Demo speeds as multiples of a base of 15 simulated seconds per real second.
export const BASE_SPEED = 15;
const SPEEDS = [1, 5, 20];

interface Props {
  state: SimState;
  blockMode: boolean;
  setBlockMode: (on: boolean) => void;
  osmTiles: boolean;
  setOsmTiles: (on: boolean) => void;
  onError: (msg: string) => void;
}

export function DemoControls({ state, blockMode, setBlockMode, osmTiles, setOsmTiles, onError }: Props) {
  const [open, setOpen] = useState(true);
  const [fp, setFp] = useState("");
  const [vehicle, setVehicle] = useState("");
  const [waveZone, setWaveZone] = useState("");
  const [waveSize, setWaveSize] = useState(5);

  const run = (p: Promise<unknown>) => p.catch((e: unknown) => onError(e instanceof Error ? e.message : String(e)));
  const send = (event: SimEvent) => run(api.event(event));

  const intactFps = state.failure_points.filter((f) => !f.failed);
  const activeVehicles = state.vehicles.filter((v) => v.status !== "lost");
  const fpChoice = intactFps.some((f) => f.id === fp) ? fp : (intactFps[0]?.id ?? "");
  const vehicleChoice = activeVehicles.some((v) => v.id === vehicle) ? vehicle : (activeVehicles[0]?.id ?? "");

  return (
    <div className="absolute left-3 top-3 z-10 w-72 rounded-lg border border-slate-700 bg-slate-950/95 text-sm shadow-xl">
      <button className="flex w-full items-center justify-between px-3 py-2 font-semibold" onClick={() => setOpen(!open)}>
        Demo controls <span className="text-slate-500">{open ? "▾" : "▸"}</span>
      </button>
      {open && (
        <div className="space-y-3 border-t border-slate-800 p-3">
          <div className="flex gap-2">
            {state.clock.running ? (
              <button className="btn flex-1 bg-amber-600" onClick={() => run(api.pause())}>
                ❚❚ Pause
              </button>
            ) : (
              <button className="btn flex-1 bg-emerald-600" onClick={() => run(api.start())}>
                ▶ Start
              </button>
            )}
            <button
              className="btn bg-slate-700"
              onClick={() => {
                if (window.confirm("Reset the scenario to t=0?")) run(api.reset());
              }}
            >
              ↺ Reset
            </button>
          </div>
          <div className="flex items-center gap-1">
            <span className="mr-1 text-slate-400">Speed</span>
            {SPEEDS.map((x) => (
              <button
                key={x}
                className={`btn flex-1 ${state.clock.speed === x * BASE_SPEED ? "bg-sky-600" : "bg-slate-800"}`}
                title={`${x * BASE_SPEED} simulated seconds per real second`}
                onClick={() => run(api.speed(x * BASE_SPEED))}
              >
                {x}×
              </button>
            ))}
          </div>

          <fieldset className="space-y-1.5">
            <legend className="text-xs uppercase tracking-wider text-slate-500">Block road</legend>
            <div className="flex gap-2">
              <select className="input flex-1" value={fpChoice} onChange={(e) => setFp(e.target.value)} disabled={!intactFps.length}>
                {intactFps.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.label}
                  </option>
                ))}
                {!intactFps.length && <option>all failed</option>}
              </select>
              <button className="btn bg-red-700" disabled={!fpChoice} onClick={() => send({ type: "block_road", failure_point: fpChoice })}>
                Fail
              </button>
            </div>
            <button className={`btn w-full ${blockMode ? "bg-red-600" : "bg-slate-800"}`} onClick={() => setBlockMode(!blockMode)}>
              {blockMode ? "Cancel road picking" : "Pick a road on the map"}
            </button>
          </fieldset>

          <fieldset className="space-y-1.5">
            <legend className="text-xs uppercase tracking-wider text-slate-500">Add SOS wave</legend>
            <div className="flex gap-2">
              <select className="input w-16" value={waveSize} onChange={(e) => setWaveSize(Number(e.target.value))}>
                {[3, 5, 10].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
              <select className="input flex-1" value={waveZone} onChange={(e) => setWaveZone(e.target.value)}>
                <option value="">random zones</option>
                {state.zones.map((z) => (
                  <option key={z.id} value={z.id}>
                    {z.id}
                    {z.cut_off ? " (cut off)" : z.flooded ? " (flooded)" : ""}
                  </option>
                ))}
              </select>
              <button
                className="btn bg-orange-600"
                onClick={() => send({ type: "add_sos_wave", count: waveSize, ...(waveZone ? { zone: waveZone } : {}) })}
              >
                Add
              </button>
            </div>
          </fieldset>

          <fieldset className="space-y-1.5">
            <legend className="text-xs uppercase tracking-wider text-slate-500">Remove vehicle</legend>
            <div className="flex gap-2">
              <select className="input flex-1" value={vehicleChoice} onChange={(e) => setVehicle(e.target.value)}>
                {activeVehicles.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.label}
                  </option>
                ))}
              </select>
              <button className="btn bg-red-700" disabled={!vehicleChoice} onClick={() => send({ type: "remove_vehicle", vehicle: vehicleChoice })}>
                Remove
              </button>
            </div>
          </fieldset>

          <label className="flex items-center gap-2 text-xs text-slate-400">
            <input type="checkbox" checked={osmTiles} onChange={(e) => setOsmTiles(e.target.checked)} />
            OSM background tiles (needs internet)
          </label>
        </div>
      )}
    </div>
  );
}
