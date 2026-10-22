# PROMETHEUS DM-01

Disaster impact forecasting and multi-agency rescue dispatch, demonstrated on a
**simulated** flash-flood scenario over real OpenStreetMap roads and hospitals in Nagpur.

Everything except road geometry and hospital locations is simulated: rainfall, flooding,
failure points, SOS calls, fleet, bed counts and casualty estimates.

## Layout

| Path | What |
| --- | --- |
| `sim/` | Builds the seed dataset (`sim/data`): OSM roads + hospitals, 12 zones, fleet |
| `backend/` | FastAPI: forecast, OR-Tools dispatch, deterministic sim engine, REST + WebSocket |
| `backend/sim/scenario.json` | Scripted scenario (hospitals, failure points, flood zones, timeline) |
| `dashboard/` | Operator dashboard: Vite + React + TypeScript + Tailwind + MapLibre GL |

## Run it

Requires Python 3.12+ and Node 20+.

```bash
# 1. Backend (http://127.0.0.1:8000)
pip install -r backend/requirements.txt
cd backend
python -m uvicorn app.main:app --port 8000

# 2. Dashboard (http://localhost:5173), in a second terminal
cd dashboard
npm install
npm run dev
```

Open http://localhost:5173 and press **Start** in the demo controls. The dashboard reaches
the backend through the Vite proxy at `/api`; set `PROMETHEUS_BACKEND` to point it elsewhere.

The map needs no internet: it draws only our own GeoJSON. "OSM background tiles" in the
demo controls adds a raster basemap when online.

For a production-style build: `npm run build && npm run preview` (serves on port 4173 with
the same `/api` proxy).

## Demo controls

| Control | Backend call |
| --- | --- |
| Start / Pause | `POST /sim/start`, `POST /sim/pause` |
| Speed 1× / 5× / 20× | `POST /sim/speed` with 15 / 75 / 300 simulated seconds per real second |
| Reset | `POST /sim/reset` (back to t=0, paused) |
| Block road | `POST /sim/event {"type":"block_road","failure_point":"FP1"}`, or pick a road on the map (`u`, `v`) |
| Add SOS wave | `POST /sim/event {"type":"add_sos_wave","count":5,"zone":"Z11"}` (seeded) |
| Remove vehicle | `POST /sim/event {"type":"remove_vehicle","vehicle":"DRO-01"}` |
| Auto-approve toggle | `POST /sim/auto-approve {"enabled": false}` |
| Approve | `POST /sim/approve` |

With auto-approve off, every re-plan that changes assignments becomes a **proposal**: the sim
clock holds until the operator approves it, so vehicles never jump. The plan panel lists what
changed (new, reassigned, unassigned calls), and every assignment has a **Why?** popover
(priority rank, terrain rule, distance/time, why not the nearest vehicle, what nearest-first
would do). Re-plans that change nothing are applied without asking.

`GET /state` returns the full state; `WS /ws` pushes it every tick (0.25 s real time).

## Rebuilding data

```bash
python sim/build_dataset.py          # OSM download (falls back to a synthetic network offline)
python backend/sim/build_scenario.py # scenario.json from the dataset
```

Both are deterministic: rebuilding gives byte-identical files.

## Tests

```bash
python -m pytest sim/tests backend/tests
cd dashboard && npm test && npm run typecheck
```

## Talking points (be upfront about these)

- **Why the optimiser wins:** with plenty of vehicles, nearest-first is fine. The optimiser
  pays off when demand exceeds supply, which is exactly what a flood produces. The scripted
  SOS waves (10–13 calls) deliberately outnumber the vehicles able to serve them.
- **"People reached"** means a first responder is on scene, not that everyone was evacuated.
- **Failure points** are modelled as flooded underpasses (Underpass A–D). On the real road
  network no four single segments isolate a zone, so each underpass takes out 1–2 adjacent
  segments; NetworkX's minimum cut picks them so that all four together cut off Z11.
- **Simplifications:** emergency vehicles may ignore one-way streets; roads inside flooded
  zones stay drivable (flooding decides which vehicle type serves a call); boats travel
  straight with a 1.3× detour factor; hospitals are a provisional pick of 7.
