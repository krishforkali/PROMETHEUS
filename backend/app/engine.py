"""Deterministic scripted simulation: clock, vehicle motion, events, re-planning.

Everything here is driven by `run_until(t)`; wall-clock time only enters via the
runner, so the same scenario always produces the same states.
"""

from __future__ import annotations

import bisect
import random
from typing import Any

from app.dispatch import Hospital, Incident, Vehicle, dispatch
from app.forecast import cut_off_zones, elevation_factors, risk, zone_forecast
from app.network import (
    LatLon,
    build_graph,
    edge_key,
    haversine_m,
    nearest_node,
    without_edges,
    zone_nodes,
    zone_of,
)

MODE_BY_TERRAIN = {"road": "road", "water": "water", "air": "air"}
TYPE_LABEL = {"ambulance": "Ambulance", "boat": "Boat", "drone": "Drone", "truck": "Truck"}
SOS_SEVERITY = range(1, 6)
SOS_KINDS = {"medical", "supplies"}
MAX_WAVE = 20
LOG_LIMIT = 200


def vehicle_label(vid: str, vtype: str) -> str:
    """'DRO-02' -> 'Drone 2'."""
    return f"{TYPE_LABEL.get(vtype, vtype.title())} {int(vid.rsplit('-', 1)[-1])}"


class Simulation:
    def __init__(
        self,
        scenario: dict[str, Any],
        roads: dict[str, Any],
        zones: list[dict[str, Any]],
        fleet: list[dict[str, Any]],
    ) -> None:
        self.graph = build_graph(roads)
        self.zones = zones
        self.zone_nodes = zone_nodes(self.graph, zones)
        self.elevation = elevation_factors(zones)
        self.vulnerability = {zid: p["vulnerability"] for zid, p in scenario["zone_params"].items()}
        self.failure_points = {fp["id"]: fp for fp in scenario["failure_points"]}
        self.flood_thresholds = {f["zone"]: f["flood_at_mm_hr"] for f in scenario["flood_zones"]}
        self.timeline = sorted(scenario["timeline"], key=lambda e: e["t"])
        self.hospitals = {
            h["id"]: {**h, "beds_available": h["capacity"]["beds_available"]} for h in scenario["hospitals"]
        }
        self.vehicles = {
            v["id"]: {
                "id": v["id"],
                "label": vehicle_label(v["id"], v["type"]),
                "type": v["type"],
                "mode": MODE_BY_TERRAIN[v["terrain"]],
                "speed_mps": v["speed_kmh"] / 3.6,
                "capacity": v["capacity"],
                "lat": v["depot"]["lat"],
                "lon": v["depot"]["lon"],
                "status": "idle",
                "legs": [],
            }
            for v in fleet
        }
        self.time_s = 0.0
        self.rain_mm_hr = 0.0
        self.flooded: set[str] = set()
        self.failed: set[str] = set()
        self.blocked: set[tuple[int, int]] = set()
        self.cut_off: set[str] = set()
        self.incidents: dict[str, dict[str, Any]] = {}
        self.plan: dict[str, Any] | None = None
        self.plan_version = 0
        self.log: list[dict[str, Any]] = []
        self._next_event = 0
        self._sos_seq = 0
        self._rng = random.Random(scenario.get("seed", 0))  # manual SOS waves
        self._gain = {"baseline": 0, "optimised": 0, "plans": 0}  # cumulative over re-plans
        self.run_until(0.0)

    # ---- clock ----------------------------------------------------------

    def step(self, dt: float) -> None:
        self.run_until(self.time_s + dt)

    def run_until(self, t: float) -> None:
        while self._next_event < len(self.timeline) and self.timeline[self._next_event]["t"] <= t:
            event = self.timeline[self._next_event]
            self._next_event += 1
            self._advance_to(event["t"])
            self._apply(event, source="timeline")
        self._advance_to(t)

    def _advance_to(self, t: float) -> None:
        """Move vehicles to time t, handling every leg arrival in time order."""
        while True:
            due = [
                (v["legs"][0]["arrive_s"], vid)
                for vid, v in self.vehicles.items()
                if v["legs"] and v["status"] != "lost" and v["legs"][0]["arrive_s"] <= t
            ]
            if not due:
                break
            arrive_s, vid = min(due)
            self._move_all(arrive_s)  # others must be in place before a possible re-plan
            self._arrive(self.vehicles[vid])
        self._move_all(t)

    def _move_all(self, t: float) -> None:
        self.time_s = max(self.time_s, t)
        for v in self.vehicles.values():
            if v["legs"] and v["status"] != "lost":
                v["lat"], v["lon"] = _position(v["legs"][0], self.time_s)

    def _arrive(self, v: dict[str, Any]) -> None:
        leg = v["legs"].pop(0)
        v["lat"], v["lon"] = leg["path"][-1]
        target = leg["to"]
        if target["kind"] == "incident":
            inc = self.incidents[target["id"]]
            if inc["status"] != "served":
                inc.update(status="served", served_s=leg["arrive_s"], served_by=v["id"])
                self._record("served", f"{v['label']} reached {inc['id']} ({inc['people']} people)")
        else:
            h = self.hospitals[target["id"]]
            h["beds_available"] = max(0, h["beds_available"] - target.get("patients", 0))
            self._record("hospital", f"{v['label']} delivered {target.get('patients', 0)} patients to {h['name']}")
        if v["legs"]:
            v["status"] = "transporting" if v["legs"][0]["to"]["kind"] == "hospital" else "en_route"
            return
        v["status"] = "idle"
        if any(i["status"] == "open" for i in self.incidents.values()):
            self._replan(f"{v['label']} free")

    # ---- events ---------------------------------------------------------

    def apply_manual(self, event: dict[str, Any]) -> dict[str, Any]:
        """Apply a dashboard event now. Raises ValueError on bad input."""
        return self._apply(event, source="manual")

    def _apply(self, event: dict[str, Any], source: str) -> dict[str, Any]:
        kind = event["type"]
        if kind == "rain":
            self.rain_mm_hr = float(event["mm_per_hr"])
            newly = {z for z, at in self.flood_thresholds.items() if self.rain_mm_hr >= at} - self.flooded
            self.flooded |= newly
            msg = f"rain {self.rain_mm_hr:g} mm/hr" + (f"; flooding {sorted(newly)}" if newly else "")
        elif kind in ("fail", "block_road"):
            msg = self._block(event)
        elif kind in ("sos_wave", "add_sos", "add_sos_wave"):
            specs = self._random_wave(event) if kind == "add_sos_wave" else event.get("incidents", [event])
            new = [self._add_incident(spec) for spec in specs]
            msg = f"{len(new)} SOS: " + ", ".join(f"{i['id']}@{i['zone']}" for i in new)
        elif kind in ("vehicle_lost", "remove_vehicle"):
            msg = self._lose_vehicle(event.get("vehicle", ""))
        else:
            raise ValueError(f"unknown event type {kind!r}")
        entry = self._record(kind, msg + ", re-planning", source)
        self._replan(kind)
        return entry

    def _block(self, event: dict[str, Any]) -> str:
        fp_id = event.get("failure_point")
        if fp_id is not None:
            if fp_id not in self.failure_points:
                raise ValueError(f"unknown failure point {fp_id!r}")
            self.failed.add(fp_id)
            edges = [edge_key(u, v) for u, v in self.failure_points[fp_id]["edges"]]
            label = f"{self.failure_points[fp_id]['label']} failed"
        else:
            u, v = event.get("u"), event.get("v")
            if u is None or v is None or not self.graph.has_edge(u, v):
                raise ValueError("block_road needs a failure_point or an existing road edge u, v")
            edges, label = [edge_key(u, v)], f"road {u}-{v} blocked"
        self.blocked.update(edges)
        before, self.cut_off = self.cut_off, cut_off_zones(self.active_graph(), self.zone_nodes, self._hospital_nodes())
        newly = sorted(self.cut_off - before)
        return label + (f"; cut off {newly}" if newly else "")

    def _add_incident(self, spec: dict[str, Any]) -> dict[str, Any]:
        severity, people, kind = int(spec["severity"]), int(spec["people"]), spec.get("kind", "medical")
        if severity not in SOS_SEVERITY or people < 1 or kind not in SOS_KINDS:
            raise ValueError("SOS needs severity 1-5, people >= 1, kind medical|supplies")
        lat, lon = float(spec["lat"]), float(spec["lon"])
        self._sos_seq += 1
        inc = {
            "id": f"SOS-{self._sos_seq:03d}",
            "lat": lat,
            "lon": lon,
            "node": nearest_node(self.graph, (lat, lon)),
            "zone": zone_of((lat, lon), self.zones),
            "severity": severity,
            "people": people,
            "kind": kind,
            "source": spec.get("source", "dashboard"),
            "created_s": self.time_s,
            "status": "open",
            "simulated": True,
        }
        self.incidents[inc["id"]] = inc
        return inc

    def _random_wave(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        """Seeded SOS wave for the demo button; optionally all in one zone."""
        count = int(event.get("count", 5))
        zone = event.get("zone")
        if not 1 <= count <= MAX_WAVE:
            raise ValueError(f"wave count must be 1-{MAX_WAVE}")
        candidates = sorted(z for z, nodes in self.zone_nodes.items() if nodes)
        if zone is not None and zone not in candidates:
            raise ValueError(f"unknown zone {zone!r}")
        specs = []
        for _ in range(count):
            node = self._rng.choice(self.zone_nodes[zone or self._rng.choice(candidates)])
            specs.append(
                {
                    "lat": self.graph.nodes[node]["lat"],
                    "lon": self.graph.nodes[node]["lon"],
                    "severity": self._rng.randint(1, 5),
                    "people": self._rng.randint(2, 40),
                    "kind": self._rng.choice(["medical", "medical", "supplies"]),
                    "source": "dashboard",
                }
            )
        return specs

    def _lose_vehicle(self, vid: str) -> str:
        if vid not in self.vehicles:
            raise ValueError(f"unknown vehicle {vid!r}")
        v = self.vehicles[vid]
        if v["status"] == "lost":
            raise ValueError(f"{vid} already lost")
        v.update(status="lost", legs=[])
        return f"{v['label']} lost"

    # ---- planning -------------------------------------------------------

    def active_graph(self):  # noqa: ANN201
        return without_edges(self.graph, self.blocked)

    def _hospital_nodes(self) -> list[int]:
        return [h["node"] for h in self.hospitals.values()]

    def _replan(self, reason: str) -> None:
        graph = self.active_graph()
        available = [v for v in self.vehicles.values() if v["status"] in ("idle", "en_route")]
        for inc in self.incidents.values():
            if inc["status"] == "assigned":
                inc["status"] = "open"
        vehicles = [
            Vehicle(
                id=v["id"],
                type=v["type"],
                mode=v["mode"],
                speed_mps=v["speed_mps"],
                capacity=v["capacity"],
                lat=v["lat"],
                lon=v["lon"],
                node=nearest_node(graph, (v["lat"], v["lon"])),
            )
            for v in available
        ]
        incidents = [
            Incident(i["id"], i["lat"], i["lon"], i["node"], i["zone"], i["severity"], i["people"], i["kind"])
            for i in sorted(self.incidents.values(), key=lambda i: (i["created_s"], i["id"]))
            if i["status"] == "open"
        ]
        hospitals = [
            Hospital(h["id"], h["name"], h["lat"], h["lon"], h["node"], h["beds_available"])
            for h in self.hospitals.values()
        ]
        self.plan = dispatch(vehicles, incidents, graph, hospitals, self.flooded, self.cut_off, t0=self.time_s)
        self.plan_version += 1
        self.plan.update(version=self.plan_version, reason=reason)
        if incidents:
            self._gain["baseline"] += self.plan["baseline"]["cost"]
            self._gain["optimised"] += self.plan["metrics"]["cost"]
            self._gain["plans"] += 1
        legs = {r["vehicle"]: r["legs"] for r in self.plan["routes"]}
        for v in available:
            v["legs"] = [{**leg, "cum": _cumulative(leg["path"])} for leg in legs.get(v["id"], [])]
            v["status"] = "en_route" if v["legs"] else "idle"
        for a in self.plan["assignments"]:
            self.incidents[a["incident"]].update(status="assigned", assigned_to=a["vehicle"], eta_s=a["eta_s"])

    # ---- output ---------------------------------------------------------

    def _record(self, kind: str, msg: str, source: str = "sim") -> dict[str, Any]:
        entry = {"t": self.time_s, "type": kind, "source": source, "message": msg}
        self.log = (self.log + [entry])[-LOG_LIMIT:]
        return entry

    def metrics(self) -> dict[str, Any]:
        served = [i for i in self.incidents.values() if i["status"] == "served"]
        waits = [i["served_s"] - i["created_s"] for i in served]
        zones = zone_forecast(self.zones, self.vulnerability, self.rain_mm_hr, self.flooded, self.cut_off)
        g = self._gain
        return {
            "people_at_risk": round(sum(z["population"] * z["risk"] for z in zones)),
            "incidents": len(self.incidents),
            "served": len(served),
            "open": sum(i["status"] != "served" for i in self.incidents.values()),
            "people_reached": sum(i["people"] for i in served),
            "avg_response_s": round(sum(waits) / len(waits), 1) if waits else None,
            "plan_gain_pct": round((g["baseline"] - g["optimised"]) / g["baseline"] * 100, 1) if g["baseline"] else None,
            "plans_compared": g["plans"],
        }

    def state(self) -> dict[str, Any]:
        return {
            "simulated": True,
            "time_s": self.time_s,
            "rain_mm_hr": self.rain_mm_hr,
            "zones": zone_forecast(self.zones, self.vulnerability, self.rain_mm_hr, self.flooded, self.cut_off),
            "failure_points": [
                {
                    **{k: fp[k] for k in ("id", "label", "name", "lat", "lon", "zone", "edges")},
                    "risk": risk(self.rain_mm_hr, self.elevation[fp["zone"]], fp["river_distance_m"]),
                    "failed": fp["id"] in self.failed,
                }
                for fp in self.failure_points.values()
            ],
            "blocked_edges": sorted(self.blocked),
            "hospitals": list(self.hospitals.values()),
            "vehicles": [
                {k: v[k] for k in ("id", "label", "type", "status", "lat", "lon", "capacity")}
                | {"target": v["legs"][0]["to"] if v["legs"] else None, "route": self._remaining_route(v)}
                for v in self.vehicles.values()
            ],
            "incidents": sorted(self.incidents.values(), key=lambda i: i["id"]),
            "plan": self.plan,
            "metrics": self.metrics(),
            "log": self.log[-50:],
            "next_event_s": self.timeline[self._next_event]["t"] if self._next_event < len(self.timeline) else None,
        }


    def _remaining_route(self, v: dict[str, Any]) -> list[LatLon]:
        """Current position plus the untravelled part of every remaining leg."""
        if not v["legs"] or v["status"] == "lost":
            return []
        first = v["legs"][0]
        done = _travelled(first, self.time_s)
        out: list[LatLon] = [(v["lat"], v["lon"])]
        out += [tuple(p) for p, c in zip(first["path"], first["cum"]) if c > done]  # type: ignore[misc]
        for leg in v["legs"][1:]:
            out += [tuple(p) for p in leg["path"]]  # type: ignore[misc]
        return out


def _cumulative(path: list[LatLon]) -> list[float]:
    out = [0.0]
    for a, b in zip(path, path[1:]):
        out.append(out[-1] + haversine_m(a, b))
    return out


def _travelled(leg: dict[str, Any], t: float) -> float:
    """Metres covered along the leg at time t, at constant speed."""
    span = leg["arrive_s"] - leg["depart_s"]
    frac = 1.0 if span <= 0 else min(max((t - leg["depart_s"]) / span, 0.0), 1.0)
    return frac * leg["cum"][-1]


def _position(leg: dict[str, Any], t: float) -> LatLon:
    """Interpolate along the leg polyline at constant speed."""
    path, cum = leg["path"], leg["cum"]
    target = _travelled(leg, t)
    k = min(bisect.bisect_left(cum, target), len(path) - 1)
    if k == 0 or cum[k] == cum[k - 1]:
        return tuple(path[k])  # type: ignore[return-value]
    f = (target - cum[k - 1]) / (cum[k] - cum[k - 1])
    (a_lat, a_lon), (b_lat, b_lon) = path[k - 1], path[k]
    return (a_lat + f * (b_lat - a_lat), a_lon + f * (b_lon - a_lon))
