"""Pure, deterministic generators for simulated PROMETHEUS seed data.

Nothing here touches the network, so it is fully unit-testable.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any

import networkx as nx

SEED = 42
CENTER: tuple[float, float] = (21.1458, 79.0882)  # (lat, lon) Nagpur city centre
RADIUS_M = 3000  # 3 km each way -> ~6 km x 6 km study area
GRID_ROWS = 3
GRID_COLS = 4

# Approximate course of the Nag river through the study area, as (lat, lon).
# Simulated: used only to derive a plausible river-distance per zone.
# Endpoints extend past the study bbox so the river fully divides it.
RIVER_LINE: list[tuple[float, float]] = [
    (21.1700, 79.0300),
    (21.1650, 79.0450),
    (21.1530, 79.0700),
    (21.1450, 79.0950),
    (21.1380, 79.1200),
    (21.1300, 79.1350),
    (21.1250, 79.1500),
]

FLEET_SPEC: dict[str, dict[str, Any]] = {
    "ambulance": {"count": 6, "capacity": 2, "speed_kmh": 40.0, "terrain": "road"},
    "boat": {"count": 3, "capacity": 8, "speed_kmh": 15.0, "terrain": "water"},
    "drone": {"count": 2, "capacity": 1, "speed_kmh": 60.0, "terrain": "air"},
    "truck": {"count": 3, "capacity": 500, "speed_kmh": 30.0, "terrain": "road"},
}


@dataclass(frozen=True)
class BBox:
    south: float
    west: float
    north: float
    east: float


def bbox_around(center: tuple[float, float], radius_m: float) -> BBox:
    """Square bbox of +/- radius_m around a (lat, lon) centre."""
    lat, lon = center
    dlat = radius_m / 111_320.0
    dlon = radius_m / (111_320.0 * math.cos(math.radians(lat)))
    return BBox(south=lat - dlat, west=lon - dlon, north=lat + dlat, east=lon + dlon)


def haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance in metres between two (lat, lon) points."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6_371_000.0 * math.asin(math.sqrt(h))


def _point_segment_distance_m(
    p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]
) -> float:
    """Distance from p to segment ab, using a local equirectangular projection."""
    k = math.cos(math.radians(p[0]))

    def xy(q: tuple[float, float]) -> tuple[float, float]:
        return (q[1] * k * 111_320.0, q[0] * 111_320.0)

    px, py = xy(p)
    ax, ay = xy(a)
    bx, by = xy(b)
    dx, dy = bx - ax, by - ay
    seg2 = dx * dx + dy * dy
    t = 0.0 if seg2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def distance_to_river_m(p: tuple[float, float], river: list[tuple[float, float]] = RIVER_LINE) -> float:
    return min(_point_segment_distance_m(p, a, b) for a, b in zip(river, river[1:]))


def make_zones(bbox: BBox, seed: int = SEED, rows: int = GRID_ROWS, cols: int = GRID_COLS) -> list[dict[str, Any]]:
    """Split bbox into a rows x cols grid with simulated attributes per zone."""
    rng = random.Random(seed)
    dlat = (bbox.north - bbox.south) / rows
    dlon = (bbox.east - bbox.west) / cols
    zones: list[dict[str, Any]] = []
    for r in range(rows):
        for c in range(cols):
            s, w = bbox.south + r * dlat, bbox.west + c * dlon
            n, e = s + dlat, w + dlon
            centroid = ((s + n) / 2, (w + e) / 2)
            river_m = distance_to_river_m(centroid)
            # Lower ground near the river; Nagpur sits ~290-330 m above sea level.
            elevation_m = 290.0 + min(river_m, 4000.0) / 4000.0 * 30.0 + rng.uniform(-4.0, 4.0)
            zones.append(
                {
                    "id": f"Z{len(zones) + 1:02d}",
                    "row": r,
                    "col": c,
                    "bounds": {"south": s, "west": w, "north": n, "east": e},
                    "centroid": {"lat": centroid[0], "lon": centroid[1]},
                    "polygon": [[w, s], [e, s], [e, n], [w, n], [w, s]],
                    "population": rng.randint(15_000, 120_000),
                    "elevation_m": round(elevation_m, 1),
                    "river_distance_m": round(river_m, 1),
                    "simulated": True,
                }
            )
    return zones


def _segments_cross(
    p1: tuple[float, float], p2: tuple[float, float], q1: tuple[float, float], q2: tuple[float, float]
) -> bool:
    """True if segment p1-p2 properly intersects segment q1-q2 (planar, lat/lon)."""

    def orient(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    d1, d2 = orient(q1, q2, p1), orient(q1, q2, p2)
    d3, d4 = orient(p1, p2, q1), orient(p1, p2, q2)
    return d1 * d2 < 0 and d3 * d4 < 0


def crosses_river(a: tuple[float, float], b: tuple[float, float], river: list[tuple[float, float]] = RIVER_LINE) -> bool:
    return any(_segments_cross(a, b, r1, r2) for r1, r2 in zip(river, river[1:]))


def make_synthetic_roads(
    bbox: BBox, seed: int = SEED, n: int = 21, n_bridges: int = 4
) -> nx.MultiDiGraph:
    """Fallback road network: an n x n two-way grid over bbox, cut by the river.

    Only n_bridges of the river-crossing segments are kept (flagged bridge=True),
    so the river is a real bottleneck. Output matches osmnx's graph schema.
    """
    rng = random.Random(seed)
    g = nx.MultiDiGraph(crs="epsg:4326", simulated=True)
    lat_step = (bbox.north - bbox.south) / (n - 1)
    lon_step = (bbox.east - bbox.west) / (n - 1)

    def nid(r: int, c: int) -> int:
        return r * n + c

    for r in range(n):
        for c in range(n):
            g.add_node(nid(r, c), y=bbox.south + r * lat_step, x=bbox.west + c * lon_step, street_count=4)

    segments = [(nid(r, c), nid(r, c + 1)) for r in range(n) for c in range(n - 1)]
    segments += [(nid(r, c), nid(r + 1, c)) for r in range(n - 1) for c in range(n)]

    def latlon(u: int) -> tuple[float, float]:
        return (g.nodes[u]["y"], g.nodes[u]["x"])

    crossing = [s for s in segments if crosses_river(latlon(s[0]), latlon(s[1]))]
    bridges = sorted(rng.sample(crossing, k=min(n_bridges, len(crossing))))
    dropped = set(crossing) - set(bridges)

    for u, v in segments:
        if (u, v) in dropped:
            continue
        attrs: dict[str, Any] = {
            "length": round(haversine_m(latlon(u), latlon(v)), 1),
            "highway": "residential",
            "bridge": False,
            "oneway": False,
        }
        if (u, v) in bridges:
            attrs.update(highway="primary", bridge=True, name=f"Synthetic bridge {bridges.index((u, v)) + 1}")
        g.add_edge(u, v, key=0, **attrs)
        g.add_edge(v, u, key=0, **attrs)
    return g


def make_synthetic_hospitals(graph: nx.MultiDiGraph, seed: int = SEED, count: int = 6) -> list[dict[str, Any]]:
    """Fallback hospitals placed on seeded random road nodes."""
    picks = random.Random(seed).sample(sorted(graph.nodes), k=min(count, graph.number_of_nodes()))
    return [
        {
            "id": f"synthetic/{i + 1}",
            "name": f"Simulated Hospital {i + 1}",
            "lat": graph.nodes[n]["y"],
            "lon": graph.nodes[n]["x"],
            "node": int(n),
            "source": "synthetic",
            "simulated": True,
        }
        for i, n in enumerate(picks)
    ]


def make_fleet(
    depot_candidates: list[dict[str, Any]],
    seed: int = SEED,
    spec: dict[str, dict[str, Any]] = FLEET_SPEC,
) -> list[dict[str, Any]]:
    """Build the simulated fleet. Each vehicle gets a depot drawn from depot_candidates.

    depot_candidates: dicts with at least "lat", "lon" and "node" (road-graph node id).
    """
    if not depot_candidates:
        raise ValueError("need at least one depot candidate")
    rng = random.Random(seed)
    fleet: list[dict[str, Any]] = []
    for vtype, cfg in spec.items():
        for i in range(cfg["count"]):
            depot = rng.choice(depot_candidates)
            fleet.append(
                {
                    "id": f"{vtype[:3].upper()}-{i + 1:02d}",
                    "type": vtype,
                    "capacity": cfg["capacity"],
                    "speed_kmh": cfg["speed_kmh"],
                    "terrain": cfg["terrain"],
                    "depot": {"lat": depot["lat"], "lon": depot["lon"], "node": depot["node"]},
                    "simulated": True,
                }
            )
    return fleet
