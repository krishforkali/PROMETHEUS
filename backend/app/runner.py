"""Wall-clock driver for the simulation: start / pause / speed, pushes state to WebSockets."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Callable

from fastapi import WebSocket

from app.data import load
from app.engine import Simulation

DEFAULT_SCENARIO = Path(__file__).resolve().parents[1] / "sim" / "scenario.json"
DEFAULT_SPEED = 30.0  # simulated seconds per real second
MAX_SPEED = 600.0
TICK_REAL_S = 0.25  # short ticks keep vehicle motion smooth at high speed


def scenario_path() -> Path:
    return Path(os.environ.get("PROMETHEUS_SCENARIO", DEFAULT_SCENARIO))


def new_simulation() -> Simulation:
    scenario = json.loads(scenario_path().read_text(encoding="utf-8"))
    return Simulation(scenario, load("roads.geojson"), load("zones.json"), load("fleet.json"))


class SimRunner:
    def __init__(self, factory: Callable[[], Simulation] = new_simulation, tick_real_s: float = TICK_REAL_S) -> None:
        self.factory = factory
        self.sim = factory()
        self.running = False
        self.speed = DEFAULT_SPEED
        self.tick_real_s = tick_real_s
        self.clients: set[WebSocket] = set()
        self._task: asyncio.Task[None] | None = None

    def status(self) -> dict[str, Any]:
        return {"running": self.running, "speed": self.speed, "time_s": self.sim.time_s}

    def state(self) -> dict[str, Any]:
        return {**self.sim.state(), "clock": self.status()}

    async def start(self) -> None:
        self.running = True
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    def pause(self) -> None:
        self.running = False

    def reset(self) -> None:
        """Pause and restart the scenario from t=0 (speed is kept)."""
        self.pause()
        self.sim = self.factory()

    def set_speed(self, speed: float) -> None:
        if not 0 < speed <= MAX_SPEED:
            raise ValueError(f"speed must be in (0, {MAX_SPEED:g}]")
        self.speed = speed

    async def _loop(self) -> None:
        while self.running:
            await asyncio.sleep(self.tick_real_s)
            if not self.running:
                break
            self.sim.step(self.tick_real_s * self.speed)
            await self.broadcast()

    async def broadcast(self) -> None:
        if not self.clients:
            return
        state = self.state()
        for ws in list(self.clients):
            try:
                await ws.send_json(state)
            except Exception:  # client went away mid-send
                self.clients.discard(ws)
