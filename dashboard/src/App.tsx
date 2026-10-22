import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import { DemoControls } from "./components/DemoControls";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { EventFeed } from "./components/EventFeed";
import { ForecastPanel } from "./components/ForecastPanel";
import { IncidentQueue } from "./components/IncidentQueue";
import { KpiBar } from "./components/KpiBar";
import { MapView } from "./components/MapView";
import { PlanPanel } from "./components/PlanPanel";
import { ResourcesPanel } from "./components/ResourcesPanel";
import type { RoadCollection, ZoneInfo } from "./types";
import { useSimState } from "./useSimState";

export default function App() {
  const { state, connection } = useSimState();
  const [zones, setZones] = useState<ZoneInfo[] | null>(null);
  const [roads, setRoads] = useState<RoadCollection | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [blockMode, setBlockMode] = useState(false);
  const [osmTiles, setOsmTiles] = useState(false);

  useEffect(() => {
    Promise.all([api.zones(), api.roads()])
      .then(([z, r]) => {
        setZones(z);
        setRoads(r);
      })
      .catch((e: unknown) => setLoadError(e instanceof Error ? e.message : String(e)));
  }, []);

  useEffect(() => {
    if (!toast) return;
    const t = window.setTimeout(() => setToast(null), 4000);
    return () => window.clearTimeout(t);
  }, [toast]);

  const onRoadClick = useCallback((u: number, v: number) => {
    setBlockMode(false);
    api.event({ type: "block_road", u, v }).catch((e: unknown) => setToast(e instanceof Error ? e.message : String(e)));
  }, []);

  if (loadError) return <Splash text={`Cannot reach the backend: ${loadError}`} />;
  if (!state || !zones || !roads) return <Splash text={connection === "open" ? "Loading map data…" : "Connecting to simulation…"} />;

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-slate-950 text-slate-100">
      <KpiBar state={state} connection={connection} />
      <div className="grid min-h-0 flex-1 grid-cols-[22rem_minmax(0,1fr)_21rem] grid-rows-[minmax(0,1fr)_17rem]">
        <aside className="row-span-2 flex min-h-0 flex-col border-r border-slate-800">
          <IncidentQueue state={state} />
        </aside>
        <main className="relative min-h-0">
          <ErrorBoundary label="Map">
            <MapView state={state} zones={zones} roads={roads} osmTiles={osmTiles} blockMode={blockMode} onRoadClick={onRoadClick} />
          </ErrorBoundary>
          <DemoControls
            state={state}
            blockMode={blockMode}
            setBlockMode={setBlockMode}
            osmTiles={osmTiles}
            setOsmTiles={setOsmTiles}
            onError={setToast}
          />
          {toast && (
            <div className="absolute bottom-4 left-1/2 z-20 -translate-x-1/2 rounded-md bg-red-700 px-4 py-2 text-sm font-semibold shadow-lg">
              {toast}
            </div>
          )}
          {state.proposal && (
            <div className="absolute left-1/2 top-3 z-20 -translate-x-1/2 rounded-md bg-amber-500 px-4 py-1.5 text-sm font-bold text-black shadow-lg">
              ⏸ Clock held: new plan v{state.proposal.version} awaiting approval
            </div>
          )}
          {connection !== "open" && (
            <div className="absolute inset-x-0 top-0 z-20 bg-amber-600 py-1 text-center text-sm font-semibold text-black">
              Connection lost — reconnecting…
            </div>
          )}
        </main>
        <aside className="row-span-2 min-h-0 overflow-y-auto border-l border-slate-800">
          <ResourcesPanel state={state} />
          <ForecastPanel state={state} />
        </aside>
        <div className="grid min-h-0 grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)] border-t border-slate-800">
          <PlanPanel state={state} onError={setToast} />
          <div className="flex min-h-0 flex-col border-l border-slate-800">
            <EventFeed state={state} />
          </div>
        </div>
      </div>
    </div>
  );
}

function Splash({ text }: { text: string }) {
  return (
    <div className="flex h-screen items-center justify-center bg-slate-950 text-lg text-slate-300">
      <div className="text-center">
        <div className="mb-2 text-2xl font-black text-orange-400">PROMETHEUS</div>
        {text}
      </div>
    </div>
  );
}
