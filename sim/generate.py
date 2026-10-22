"""Pure, deterministic generators for simulated PROMETHEUS seed data.

Nothing here touches the network, so it is fully unit-testable.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any

SEED = 42
CENTER: tuple[float, float] = (21.1458, 79.0882)  # (lat, lon) Nagpur city centre
RADIUS_M = 5000  # 5 km each way -> ~10 km x 10 km study area
GRID_ROWS = 3
GRID_COLS = 4

# Approximate course of the Nag river through the study area, as (lat, lon).
# Simulated: used only to derive a plausible river-distance per zone.
RIVER_LINE: list[tuple[float, float]] = [
    (21.1650, 79.0450),
    (21.1530, 79.0700),
    (21.1450, 79.0950),
    (21.1380, 79.1200),
    (21.1300, 79.1350),
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
