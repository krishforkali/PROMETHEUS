"""Simple, transparent flood forecast. No ML: every number is a formula.

risk       = rain_factor x (1 - elevation_factor) x river_closeness   (0..1)
casualties = population x hazard x vulnerability, as a low/expected/high band
cut-off    = zone whose road nodes mostly cannot reach any hospital
"""

from __future__ import annotations

from typing import Any, Iterable

import networkx as nx

from app.network import reachable_from

RAIN_SATURATION_MM_HR = 100.0  # rainfall at which rain_factor = 1
RIVER_INFLUENCE_M = 3000.0  # beyond this the river adds no risk
MAX_ELEVATION_RELIEF = 0.8  # highest ground still keeps 20% of the risk
CUT_OFF_FRACTION = 0.5  # zone is cut off when < 50% of its nodes reach a hospital
CASUALTY_BAND = {"low": 0.5, "expected": 1.0, "high": 1.8}


def elevation_factors(zones: list[dict[str, Any]]) -> dict[str, float]:
    """0 for the lowest zone, MAX_ELEVATION_RELIEF for the highest."""
    elevs = [z["elevation_m"] for z in zones]
    lo, hi = min(elevs), max(elevs)
    span = (hi - lo) or 1.0
    return {z["id"]: (z["elevation_m"] - lo) / span * MAX_ELEVATION_RELIEF for z in zones}


def rain_factor(rain_mm_hr: float) -> float:
    return min(max(rain_mm_hr, 0.0) / RAIN_SATURATION_MM_HR, 1.0)


def river_closeness(river_distance_m: float) -> float:
    return max(0.0, 1.0 - river_distance_m / RIVER_INFLUENCE_M)


def risk(rain_mm_hr: float, elevation_factor: float, river_distance_m: float) -> float:
    return round(rain_factor(rain_mm_hr) * (1.0 - elevation_factor) * river_closeness(river_distance_m), 4)


def casualties(population: int, hazard: float, vulnerability: float) -> dict[str, int]:
    expected = population * hazard * vulnerability
    return {k: round(expected * f) for k, f in CASUALTY_BAND.items()}


def cut_off_zones(
    active: nx.Graph, zone_nodes: dict[str, list[int]], hospital_nodes: Iterable[int]
) -> set[str]:
    reach = reachable_from(active, hospital_nodes)
    return {
        zid
        for zid, nodes in zone_nodes.items()
        if nodes and sum(n in reach for n in nodes) / len(nodes) < CUT_OFF_FRACTION
    }


def zone_forecast(
    zones: list[dict[str, Any]],
    vulnerability: dict[str, float],
    rain_mm_hr: float,
    flooded: set[str],
    cut_off: set[str],
) -> list[dict[str, Any]]:
    elev = elevation_factors(zones)
    out = []
    for z in zones:
        hazard = risk(rain_mm_hr, elev[z["id"]], z["river_distance_m"])
        out.append(
            {
                "id": z["id"],
                "population": z["population"],
                "risk": hazard,
                "casualties": casualties(z["population"], hazard, vulnerability[z["id"]]),
                "flooded": z["id"] in flooded,
                "cut_off": z["id"] in cut_off,
                "simulated": True,
            }
        )
    return out
