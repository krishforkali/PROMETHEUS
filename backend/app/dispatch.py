"""Multi-vehicle dispatch: OR-Tools VRP, compared against a nearest-first baseline.

Objective (used by both methods, so they are comparable):
    cost = sum(priority x arrival_s) over served incidents
         + sum(priority x DROP_PENALTY_S) over dropped incidents
where priority = severity x people.

Terrain rules: cut-off zones -> drones (or boats if also flooded); flooded zones
-> boats; otherwise medical -> ambulance, supplies -> truck. Ambulances must be
able to reach a hospital with free beds and end their route there.
Road vehicles use NetworkX shortest paths on the current graph; drones fly
straight; boats go straight with a detour factor.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import networkx as nx
from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from app.network import LatLon, haversine_m, path_coords

MAX_STOPS = {"ambulance": 1, "boat": 3, "drone": 2, "truck": 4}
WATER_DETOUR = 1.3
DROP_PENALTY_S = 3 * 3600
HORIZON_S = 24 * 3600
SOLVER_TIME_LIMIT_S = 5


@dataclass(frozen=True)
class Vehicle:
    id: str
    type: str
    mode: str  # road | water | air
    speed_mps: float
    capacity: int
    lat: float
    lon: float
    node: int
    ready_s: int = 0


@dataclass(frozen=True)
class Incident:
    id: str
    lat: float
    lon: float
    node: int
    zone: str
    severity: int
    people: int
    kind: str  # medical | supplies

    @property
    def priority(self) -> int:
        return self.severity * self.people


@dataclass(frozen=True)
class Hospital:
    id: str
    name: str
    lat: float
    lon: float
    node: int
    beds_available: int


@dataclass
class Problem:
    vehicles: list[Vehicle]
    incidents: list[Incident]
    times: list[list[list[int]]]  # times[v][a][b]; location 0 = vehicle start, i+1 = incident i
    eligible: list[set[int]]  # incident indices each vehicle may serve


Routes = dict[str, list[int]]  # vehicle id -> ordered incident indices


def eligible_types(inc: Incident, flooded: set[str], cut_off: set[str]) -> set[str]:
    if inc.zone in cut_off:
        return {"drone", "boat"} if inc.zone in flooded else {"drone"}
    if inc.zone in flooded:
        return {"boat"}
    return {"ambulance"} if inc.kind == "medical" else {"truck"}


class RoadDistances:
    """Cached single-source Dijkstra distances (metres) on one graph."""

    def __init__(self, graph: nx.Graph) -> None:
        self.graph = graph
        self._cache: dict[int, dict[int, float]] = {}

    def metres(self, a: int, b: int) -> float | None:
        if a not in self._cache:
            self._cache[a] = nx.single_source_dijkstra_path_length(self.graph, a, weight="length")
        return self._cache[a].get(b)


def travel_s(roads: RoadDistances, v: Vehicle, a: LatLon, a_node: int, b: LatLon, b_node: int) -> int | None:
    if v.mode == "road":
        m = roads.metres(a_node, b_node)
    else:
        m = haversine_m(a, b) * (WATER_DETOUR if v.mode == "water" else 1.0)
    return None if m is None else math.ceil(m / v.speed_mps)


def nearest_hospital(
    roads: RoadDistances, node: int, hospitals: list[Hospital], beds: dict[str, int]
) -> tuple[Hospital, float] | None:
    options = [(d, h.id, h) for h in hospitals if beds[h.id] > 0 and (d := roads.metres(node, h.node)) is not None]
    if not options:
        return None
    d, _, h = min(options)
    return h, d


def build_problem(
    vehicles: list[Vehicle],
    incidents: list[Incident],
    roads: RoadDistances,
    hospitals: list[Hospital],
    flooded: set[str],
    cut_off: set[str],
) -> Problem:
    beds = {h.id: h.beds_available for h in hospitals}
    times, eligible = [], []
    for v in vehicles:
        locs = [((v.lat, v.lon), v.node)] + [((i.lat, i.lon), i.node) for i in incidents]
        t = [[0 if a == b else travel_s(roads, v, *locs[a], *locs[b]) for b in range(len(locs))] for a in range(len(locs))]
        times.append(t)
        ok = set()
        for idx, inc in enumerate(incidents):
            if v.type not in eligible_types(inc, flooded, cut_off) or t[0][idx + 1] is None:
                continue
            if v.type == "ambulance" and nearest_hospital(roads, inc.node, hospitals, beds) is None:
                continue
            ok.add(idx)
        eligible.append(ok)
    return Problem(vehicles, incidents, times, eligible)


def arrivals(p: Problem, vi: int, seq: list[int]) -> list[int]:
    t, here, out = p.vehicles[vi].ready_s, 0, []
    for i in seq:
        t += p.times[vi][here][i + 1]
        out.append(t)
        here = i + 1
    return out


def score(p: Problem, routes: Routes) -> dict[str, Any]:
    vidx = {v.id: k for k, v in enumerate(p.vehicles)}
    served: dict[int, int] = {}
    for vid, seq in routes.items():
        served.update(zip(seq, arrivals(p, vidx[vid], seq)))
    cost = sum(p.incidents[i].priority * t for i, t in served.items())
    cost += sum(inc.priority * DROP_PENALTY_S for i, inc in enumerate(p.incidents) if i not in served)
    return {
        "served": len(served),
        "dropped": len(p.incidents) - len(served),
        "people_reached": sum(p.incidents[i].people for i in served),
        "avg_response_s": round(sum(served.values()) / len(served), 1) if served else None,
        "cost": cost,
    }


def nearest_first(p: Problem) -> Routes:
    """Baseline: incidents in arrival order, each to the vehicle that can get there soonest."""
    routes: Routes = {v.id: [] for v in p.vehicles}
    clock = [v.ready_s for v in p.vehicles]
    here = [0] * len(p.vehicles)
    for i in range(len(p.incidents)):
        best: tuple[int, str, int] | None = None
        for vi, v in enumerate(p.vehicles):
            if i not in p.eligible[vi] or len(routes[v.id]) >= MAX_STOPS[v.type]:
                continue
            cand = (clock[vi] + p.times[vi][here[vi]][i + 1], v.id, vi)
            best = cand if best is None or cand < best else best
        if best is not None:
            t, vid, vi = best
            routes[vid].append(i)
            clock[vi], here[vi] = t, i + 1
    return routes


def optimise(p: Problem, initial: Routes) -> Routes | None:
    """OR-Tools VRP warm-started from `initial`. Returns None if no solution."""
    nv, ni = len(p.vehicles), len(p.incidents)
    if nv == 0 or ni == 0:
        return None
    end = nv + ni
    manager = pywrapcp.RoutingIndexManager(end + 1, nv, list(range(nv)), [end] * nv)
    routing = pywrapcp.RoutingModel(manager)

    def make_transit(vi: int):  # noqa: ANN202
        def transit(from_index: int, to_index: int) -> int:
            a, b = manager.IndexToNode(from_index), manager.IndexToNode(to_index)
            if b == end:
                return 0
            la = 0 if a == vi else a - nv + 1 if nv <= a < end else None
            lb = b - nv + 1 if nv <= b < end else None
            if la is None or lb is None:
                return HORIZON_S
            t = p.times[vi][la][lb]
            return HORIZON_S if t is None else t

        return transit

    transits = [make_transit(vi) for vi in range(nv)]  # keep callables alive
    callbacks = [routing.RegisterTransitCallback(f) for f in transits]
    for vi, cb in enumerate(callbacks):
        routing.SetArcCostEvaluatorOfVehicle(cb, vi)
    routing.AddDimensionWithVehicleTransits(callbacks, 0, HORIZON_S, False, "time")
    time_dim = routing.GetDimensionOrDie("time")
    for vi, v in enumerate(p.vehicles):
        time_dim.CumulVar(routing.Start(vi)).SetRange(v.ready_s, v.ready_s)

    def is_stop(index: int) -> int:
        return 1 if nv <= manager.IndexToNode(index) < end else 0

    stop_cb = routing.RegisterUnaryTransitCallback(is_stop)
    routing.AddDimensionWithVehicleCapacity(stop_cb, 0, [MAX_STOPS[v.type] for v in p.vehicles], True, "stops")

    for i, inc in enumerate(p.incidents):
        index = manager.NodeToIndex(nv + i)
        routing.VehicleVar(index).SetValues([-1] + [vi for vi in range(nv) if i in p.eligible[vi]])
        routing.AddDisjunction([index], inc.priority * DROP_PENALTY_S)
        time_dim.SetCumulVarSoftUpperBound(index, 0, inc.priority)

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GREEDY_DESCENT
    params.time_limit.seconds = SOLVER_TIME_LIMIT_S
    routing.CloseModelWithParameters(params)

    start = routing.ReadAssignmentFromRoutes(
        [[manager.NodeToIndex(nv + i) for i in initial[v.id]] for v in p.vehicles], True
    )
    solution = routing.SolveFromAssignmentWithParameters(start, params) if start else routing.SolveWithParameters(params)
    if solution is None:
        return None

    routes: Routes = {}
    for vi, v in enumerate(p.vehicles):
        seq, index = [], solution.Value(routing.NextVar(routing.Start(vi)))
        while not routing.IsEnd(index):
            seq.append(manager.IndexToNode(index) - nv)
            index = solution.Value(routing.NextVar(index))
        routes[v.id] = seq
    return routes


def _leg_path(graph: nx.Graph, v: Vehicle, a: LatLon, a_node: int, b: LatLon, b_node: int) -> list[LatLon]:
    if v.mode != "road":
        return [a, b]
    nodes = nx.shortest_path(graph, a_node, b_node, weight="length")
    return [a] + path_coords(graph, nodes)


def terrain_reason(inc: Incident, flooded: set[str], cut_off: set[str]) -> str:
    """Plain-language version of eligible_types for the 'Why?' popover."""
    if inc.zone in cut_off:
        extra = " or boats" if inc.zone in flooded else ""
        return f"{inc.zone} is cut off from every hospital by road, so only drones{extra} can reach it"
    if inc.zone in flooded:
        return f"{inc.zone} is flooded, so only boats can reach it"
    if inc.kind == "medical":
        return "Medical call on a connected road: ambulance, which then takes patients to a hospital with free beds"
    return "Supplies call on a connected road: ration truck"


def explain(p: Problem, routes: Routes, baseline: Routes, roads: RoadDistances, t0: float,
            flooded: set[str], cut_off: set[str]) -> dict[str, dict[str, Any]]:
    """Per-incident reasons: priority rank, terrain rule, travel, nearest vehicle, baseline choice."""
    vidx = {v.id: k for k, v in enumerate(p.vehicles)}
    base_by_inc = {i: (vid, t) for vid, seq in baseline.items() for i, t in zip(seq, arrivals(p, vidx[vid], seq))}
    planned = [i for seq in routes.values() for i in seq]
    rank = {i: r + 1 for r, i in enumerate(sorted(planned, key=lambda i: (-p.incidents[i].priority, i)))}
    out: dict[str, dict[str, Any]] = {}
    for vid, seq in routes.items():
        vi = vidx[vid]
        v = p.vehicles[vi]
        here, here_pt, here_node = 0, (v.lat, v.lon), v.node
        for stop, i in enumerate(seq, 1):
            inc = p.incidents[i]
            metres = roads.metres(here_node, inc.node) if v.mode == "road" else haversine_m(here_pt, (inc.lat, inc.lon))
            near_t, near_id = min(
                (p.vehicles[j].ready_s + p.times[j][0][i + 1], p.vehicles[j].id)
                for j in range(len(p.vehicles))
                if i in p.eligible[j]
            )
            base = base_by_inc.get(i)
            out[inc.id] = {
                "priority": inc.priority,
                "rank": rank[i],
                "of": len(planned),
                "rule": terrain_reason(inc, flooded, cut_off),
                "mode": v.mode,
                "stop": stop,
                "travel_s": p.times[vi][here][i + 1],
                "distance_m": round(metres or 0),
                "nearest": {
                    "vehicle": near_id,
                    "travel_s": near_t,
                    "busy_with": [p.incidents[k].id for k in routes.get(near_id, [])] if near_id != vid else [],
                },
                "baseline": {"vehicle": base[0], "eta_s": t0 + base[1]} if base else None,
            }
            here, here_pt, here_node = i + 1, (inc.lat, inc.lon), inc.node
    return out


def _pct(better: float | None, worse: float | None, higher_is_better: bool = False) -> float | None:
    if better is None or worse is None or worse == 0:
        return None
    return round(((better - worse) if higher_is_better else (worse - better)) / worse * 100, 1)


def dispatch(
    vehicles: list[Vehicle],
    incidents: list[Incident],
    graph: nx.Graph,
    hospitals: list[Hospital],
    flooded: set[str],
    cut_off: set[str],
    t0: float = 0.0,
) -> dict[str, Any]:
    """Plan routes; all times in the result are absolute (t0 + offset)."""
    roads = RoadDistances(graph)
    p = build_problem(vehicles, incidents, roads, hospitals, flooded, cut_off)
    baseline = nearest_first(p)
    base_score = score(p, baseline)
    routes, solver = baseline, "baseline"
    optimised = optimise(p, baseline)
    if optimised is not None and score(p, optimised)["cost"] <= base_score["cost"]:
        routes, solver = optimised, "or-tools"
    opt_score = score(p, routes)
    why = explain(p, routes, baseline, roads, t0, flooded, cut_off)

    beds = {h.id: h.beds_available for h in hospitals}
    assignments, plan_routes = [], []
    for vi, v in enumerate(p.vehicles):
        seq = routes[v.id]
        if not seq:
            continue
        legs, here, here_node, depart = [], (v.lat, v.lon), v.node, v.ready_s
        for i, arrive in zip(seq, arrivals(p, vi, seq)):
            inc = p.incidents[i]
            legs.append(
                {
                    "to": {"kind": "incident", "id": inc.id},
                    "depart_s": t0 + depart,
                    "arrive_s": t0 + arrive,
                    "path": _leg_path(graph, v, here, here_node, (inc.lat, inc.lon), inc.node),
                }
            )
            assignments.append({"vehicle": v.id, "incident": inc.id, "eta_s": t0 + arrive, "why": why[inc.id]})
            here, here_node, depart = (inc.lat, inc.lon), inc.node, arrive
        if v.type == "ambulance":
            found = nearest_hospital(roads, here_node, hospitals, beds)
            if found is not None:
                h, metres = found
                patients = min(v.capacity, p.incidents[seq[-1]].people, beds[h.id])
                beds[h.id] -= patients
                assignments[-1]["why"]["hospital"] = {"id": h.id, "name": h.name, "beds_free": beds[h.id] + patients}
                arrive = depart + math.ceil(metres / v.speed_mps)
                legs.append(
                    {
                        "to": {"kind": "hospital", "id": h.id, "patients": patients},
                        "depart_s": t0 + depart,
                        "arrive_s": t0 + arrive,
                        "path": _leg_path(graph, v, here, here_node, (h.lat, h.lon), h.node),
                    }
                )
        plan_routes.append({"vehicle": v.id, "type": v.type, "legs": legs})

    served_ids = {a["incident"] for a in assignments}
    return {
        "t0": t0,
        "solver": solver,
        "assignments": assignments,
        "routes": plan_routes,
        "dropped": [inc.id for inc in p.incidents if inc.id not in served_ids],
        "metrics": opt_score,
        "baseline": {"method": "nearest-first", **base_score},
        "improvement_pct": {
            "cost": _pct(opt_score["cost"], base_score["cost"]),
            "avg_response": _pct(opt_score["avg_response_s"], base_score["avg_response_s"]),
            "people_reached": _pct(opt_score["people_reached"], base_score["people_reached"], higher_is_better=True),
        },
    }
