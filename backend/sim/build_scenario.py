"""Build backend/sim/scenario.json: a scripted, deterministic flood scenario (simulated).

Usage:  python backend/sim/build_scenario.py

Failure points: NetworkX minimum edge cut between a zone's core and every
hospital. No small set of single road segments isolates a zone on the real
network, so the cut segments are grouped by direction into N_FAILURE_POINTS
locations (e.g. an underpass or embankment taking out adjacent segments).
Failing all of them cuts the zone off.
"""

from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "sim")]

import networkx as nx  # noqa: E402

from app.data import load  # noqa: E402
from app.forecast import elevation_factors, river_closeness  # noqa: E402
from app.network import Edge, build_graph, edge_key, haversine_m, pos, zone_nodes, zone_of  # noqa: E402
from generate import distance_to_river_m  # noqa: E402  (top-level sim/generate.py)

SEED = 42
OUT = Path(__file__).parent / "scenario.json"
# Provisional pick from the 15 filtered hospitals: all emergency=yes sites except the
# duplicate GMC campus entry, plus two to cover the west of the study area.
HOSPITALS = [
    "Central India Institute Of Medical Sciences",
    "Ganga Care Hospital Limited",
    "Govt. Medical College",
    "Harishchandra Healthcare Pvt Ltd",
    "Indira Gandhi Medical College",
    "Indira Gandhi Medical College & Hospital",
    "Nagpur Super Speciality Hospital",
]
N_FAILURE_POINTS = 4
CORE_RADIUS_M = 800.0
MIN_ISOLATED = 0.9
N_FLOOD_ZONES = 4
FLOOD_THRESHOLDS_MM_HR = [30, 45, 60, 75]


def pick_hospitals(all_hospitals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_name = {h["name"]: h for h in all_hospitals}
    missing = [n for n in HOSPITALS if n not in by_name]
    if missing:
        raise ValueError(f"hospitals not in dataset: {missing}")
    return [{**by_name[n], "provisional": True} for n in HOSPITALS]


def min_cut(g: nx.Graph, sources: set[int], sinks: set[int]) -> tuple[list[Edge], set[int]]:
    """Fewest road segments separating `sources` from `sinks`; returns (cut, source side)."""
    d = nx.DiGraph()
    for u, v in g.edges:
        d.add_edge(u, v, capacity=1)
        d.add_edge(v, u, capacity=1)
    for n in sources:
        d.add_edge("SRC", n)  # no capacity attribute = infinite
    for n in sinks:
        d.add_edge(n, "SNK")
    _, (side, _) = nx.minimum_cut(d, "SRC", "SNK")
    cut = sorted(edge_key(u, v) for u, v in g.edges if (u in side) != (v in side))
    return cut, side - {"SRC"}


def choose_cut(
    g: nx.Graph, zones: list[dict[str, Any]], znodes: dict[str, list[int]], hospital_nodes: set[int]
) -> tuple[str, list[Edge]]:
    """Zone isolated (>= MIN_ISOLATED of its nodes) by the smallest cut."""
    best: tuple[int, str, list[Edge]] | None = None
    for z in zones:
        centre = (z["centroid"]["lat"], z["centroid"]["lon"])
        core = {n for n in znodes[z["id"]] if haversine_m(pos(g, n), centre) <= CORE_RADIUS_M}
        if not core or core & hospital_nodes:
            continue
        cut, side = min_cut(g, core, hospital_nodes)
        isolated = sum(n in side for n in znodes[z["id"]]) / len(znodes[z["id"]])
        if isolated >= MIN_ISOLATED and (best is None or (len(cut), z["id"]) < best[:2]):
            best = (len(cut), z["id"], cut)
    if best is None:
        raise RuntimeError("no zone can be isolated")
    return best[1], best[2]


def _midpoint(g: nx.Graph, e: Edge) -> tuple[float, float]:
    coords = g.edges[e]["coords"]
    return coords[len(coords) // 2]


def group_by_direction(g: nx.Graph, cut: list[Edge], centre: tuple[float, float], k: int) -> list[list[Edge]]:
    """Split cut edges into k groups at the k largest angular gaps around the zone centre."""
    def angle(e: Edge) -> float:
        lat, lon = _midpoint(g, e)
        return math.atan2(lat - centre[0], (lon - centre[1]) * math.cos(math.radians(centre[0])))

    ordered = sorted(cut, key=lambda e: (angle(e), e))
    if len(ordered) <= k:
        return [[e] for e in ordered]
    angles = [angle(e) for e in ordered]
    gaps = [((angles[(i + 1) % len(ordered)] - angles[i]) % (2 * math.pi), i) for i in range(len(ordered))]
    splits = sorted(i for _, i in sorted(gaps, reverse=True)[:k])
    groups = []
    for a, b in zip(splits, splits[1:] + [splits[0] + len(ordered)]):
        groups.append([ordered[j % len(ordered)] for j in range(a + 1, b + 1)])
    return sorted(groups, key=lambda grp: grp[0])


def failure_points(g: nx.Graph, zones: list[dict[str, Any]], target: str, cut: list[Edge]) -> list[dict[str, Any]]:
    z = next(z for z in zones if z["id"] == target)
    groups = group_by_direction(g, cut, (z["centroid"]["lat"], z["centroid"]["lon"]), N_FAILURE_POINTS)
    out = []
    for n, group in enumerate(groups, 1):
        mids = [_midpoint(g, e) for e in group]
        lat, lon = sum(m[0] for m in mids) / len(mids), sum(m[1] for m in mids) / len(mids)
        names = sorted({g.edges[e]["name"] for e in group if g.edges[e]["name"]})
        out.append(
            {
                "id": f"FP{n}",
                "name": " / ".join(names) if names else f"Unnamed road near {target}",
                "lat": lat,
                "lon": lon,
                "zone": zone_of((lat, lon), zones),
                "edges": [list(e) for e in group],
                "river_distance_m": round(min(distance_to_river_m(c) for e in group for c in g.edges[e]["coords"]), 1),
                "isolates_zone": target,
                "simulated": True,
            }
        )
    return out


def flood_zones(zones: list[dict[str, Any]]) -> list[dict[str, Any]]:
    elev = elevation_factors(zones)
    ranked = sorted(zones, key=lambda z: (-(1 - elev[z["id"]]) * river_closeness(z["river_distance_m"]), z["id"]))
    return [
        {"zone": z["id"], "flood_at_mm_hr": at, "simulated": True}
        for z, at in zip(ranked[:N_FLOOD_ZONES], FLOOD_THRESHOLDS_MM_HR)
    ]


def sos(rng: random.Random, g: nx.Graph, znodes: dict[str, list[int]], zone: str) -> dict[str, Any]:
    lat, lon = pos(g, rng.choice(znodes[zone]))
    return {
        "zone": zone,
        "lat": lat,
        "lon": lon,
        "severity": rng.randint(1, 5),
        "people": rng.randint(2, 40),
        "kind": rng.choice(["medical", "medical", "supplies"]),
        "source": rng.choice(["app", "ivr", "sms", "dashboard"]),
    }


def timeline(
    rng: random.Random,
    g: nx.Graph,
    znodes: dict[str, list[int]],
    fps: list[dict[str, Any]],
    floods: list[dict[str, Any]],
    target: str,
) -> list[dict[str, Any]]:
    flood_ids = [f["zone"] for f in floods]
    dry = sorted(z for z, nodes in znodes.items() if nodes and z not in flood_ids and z != target)

    def wave(t: int, zones: list[str]) -> dict[str, Any]:
        return {"t": t, "type": "sos_wave", "incidents": [sos(rng, g, znodes, z) for z in zones]}

    # Waves outnumber the vehicles that can serve them, so dispatch has real trade-offs.
    return [
        {"t": 0, "type": "rain", "mm_per_hr": 15},
        {"t": 300, "type": "rain", "mm_per_hr": 45},
        wave(600, [flood_ids[0], flood_ids[0], flood_ids[1], flood_ids[1], target, *rng.choices(dry, k=8)]),
        {"t": 900, "type": "rain", "mm_per_hr": 65},
        {"t": 1200, "type": "fail", "failure_point": fps[0]["id"]},
        {"t": 1500, "type": "fail", "failure_point": fps[1]["id"]},
        wave(1800, [flood_ids[2], flood_ids[2], flood_ids[0], target, target, *rng.choices(dry, k=6)]),
        {"t": 2100, "type": "fail", "failure_point": fps[2]["id"]},
        {"t": 2400, "type": "fail", "failure_point": fps[3]["id"]},
        {"t": 2700, "type": "vehicle_lost", "vehicle": "DRO-01"},
        {"t": 2800, "type": "rain", "mm_per_hr": 80},
        wave(3000, [target, target, target, flood_ids[3], flood_ids[1], *rng.choices(dry, k=5)]),
        {"t": 3300, "type": "rain", "mm_per_hr": 40},
    ]


def build() -> dict[str, Any]:
    rng = random.Random(SEED)
    zones = load("zones.json")
    g = build_graph(load("roads.geojson"))
    znodes = zone_nodes(g, zones)
    hospitals = pick_hospitals(load("hospitals.json"))
    target, cut = choose_cut(g, zones, znodes, {h["node"] for h in hospitals})
    fps = failure_points(g, zones, target, cut)
    floods = flood_zones(zones)
    return {
        "name": "Nag river flash flood (scripted)",
        "simulated": True,
        "seed": SEED,
        "notes": "All events, failures, SOS calls and bed counts are simulated. Hospitals are a provisional pick.",
        "hospitals": hospitals,
        "failure_points": fps,
        "flood_zones": floods,
        "zone_params": {z["id"]: {"vulnerability": round(rng.uniform(0.002, 0.008), 4)} for z in zones},
        "timeline": timeline(rng, g, znodes, fps, floods, target),
    }


if __name__ == "__main__":
    scenario = build()
    OUT.write_text(json.dumps(scenario, indent=1), encoding="utf-8")
    fps = scenario["failure_points"]
    print(f"Wrote {OUT}: {len(scenario['hospitals'])} hospitals, {len(fps)} failure points isolating "
          f"{fps[0]['isolates_zone']}, flood zones {[f['zone'] for f in scenario['flood_zones']]}")
