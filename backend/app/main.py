from __future__ import annotations

from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from app.data import load
from app.runner import SimRunner

app = FastAPI(title="PROMETHEUS DM-01")


def _get(name: str) -> Any:
    try:
        return load(name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def get_runner(app_: FastAPI) -> SimRunner:
    if getattr(app_.state, "runner", None) is None:
        app_.state.runner = SimRunner()
    return app_.state.runner


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/zones")
def zones() -> list[dict[str, Any]]:
    return _get("zones.json")


@app.get("/fleet")
def fleet() -> list[dict[str, Any]]:
    return _get("fleet.json")


@app.get("/hospitals")
def hospitals() -> list[dict[str, Any]]:
    return _get("hospitals.json")


@app.get("/roads")
def roads() -> dict[str, Any]:
    return _get("roads.geojson")


class SpeedBody(BaseModel):
    speed: float


class EventBody(BaseModel):
    type: Literal["block_road", "add_sos", "remove_vehicle"]
    failure_point: str | None = None
    u: int | None = None
    v: int | None = None
    lat: float | None = None
    lon: float | None = None
    severity: int | None = None
    people: int | None = None
    kind: str = "medical"
    vehicle: str | None = None


@app.post("/sim/start")
async def sim_start(request: Request) -> dict[str, Any]:
    runner = get_runner(request.app)
    await runner.start()
    return runner.status()


@app.post("/sim/pause")
def sim_pause(request: Request) -> dict[str, Any]:
    runner = get_runner(request.app)
    runner.pause()
    return runner.status()


@app.post("/sim/speed")
def sim_speed(body: SpeedBody, request: Request) -> dict[str, Any]:
    runner = get_runner(request.app)
    try:
        runner.set_speed(body.speed)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return runner.status()


@app.post("/sim/event")
async def sim_event(body: EventBody, request: Request) -> dict[str, Any]:
    runner = get_runner(request.app)
    event = body.model_dump(exclude_none=True)
    if body.type == "add_sos" and None in (body.lat, body.lon, body.severity, body.people):
        raise HTTPException(status_code=400, detail="add_sos needs lat, lon, severity, people")
    try:
        entry = runner.sim.apply_manual(event)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await runner.broadcast()
    return {"event": entry, "plan_version": runner.sim.plan_version}


@app.get("/state")
def state(request: Request) -> dict[str, Any]:
    return get_runner(request.app).state()


@app.websocket("/ws")
async def ws(websocket: WebSocket) -> None:
    runner = get_runner(websocket.app)
    await websocket.accept()
    runner.clients.add(websocket)
    try:
        await websocket.send_json(runner.state())
        while True:
            await websocket.receive_text()  # keep the connection open; client messages are ignored
    except WebSocketDisconnect:
        pass
    finally:
        runner.clients.discard(websocket)
