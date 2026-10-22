"""Road-network helpers on the major-road graph.

Emergency vehicles may ignore one-way restrictions, so routing uses an
undirected graph. Edge keys are normalised to (min, max) node ids.
"""

from __future__ import annotations

import math
from typing import Any, Iterable

import networkx as nx

LatLon = tuple[float, float]
Edge = tuple[int, int]


def haversine_m(a: LatLon, b: LatLon) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    return 2 * 6_371_000.0 * math.asin(math.sqrt(h))


def edge_key(u: int, v: int) -> Edge:
    return (u, v) if u <= v else (v, u)


def build_graph(roads: dict[str, Any]) -> nx.Graph:
    """Undirected graph from roads.geojson, keeping the shortest of parallel edges."""
    g = nx.Graph()
    for f in roads["features"]:
        p = f["properties"]
        coords = [(lat, lon) for lon, lat in f["geometry"]["coordinates"]]
        u, v = p["u"], p["v"]
        g.add_node(u, lat=coords[0][0], lon=coords[0][1])
        g.add_node(v, lat=coords[-1][0], lon=coords[-1][1])
        if g.has_edge(u, v) and g.edges[u, v]["length"] <= p["length_m"]:
            continue
        g.add_edge(u, v, length=p["length_m"], name=p["name"], bridge=p["bridge"], coords=coords, start=u)
    return g


def pos(g: nx.Graph, n: int) -> LatLon:
    return (g.nodes[n]["lat"], g.nodes[n]["lon"])


def nearest_node(g: nx.Graph, p: LatLon) -> int:
    return min(g.nodes, key=lambda n: (haversine_m(p, pos(g, n)), n))


def without_edges(g: nx.Graph, blocked: Iterable[Edge]) -> nx.Graph:
    h = g.copy()
    h.remove_edges_from(e for e in blocked if h.has_edge(*e))
    return h


def path_coords(g: nx.Graph, path: list[int]) -> list[LatLon]:
    """Full polyline for a node path, following each edge's geometry."""
    if len(path) == 1:
        return [pos(g, path[0])]
    out: list[LatLon] = []
    for a, b in zip(path, path[1:]):
        data = g.edges[a, b]
        coords = data["coords"] if data["start"] == a else data["coords"][::-1]
        out.extend(coords if not out else coords[1:])
    return out


def reachable_from(g: nx.Graph, sources: Iterable[int]) -> set[int]:
    reach: set[int] = set()
    for s in sources:
        if s in g and s not in reach:
            reach |= nx.node_connected_component(g, s)
    return reach


def zone_nodes(g: nx.Graph, zones: list[dict[str, Any]]) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {z["id"]: [] for z in zones}
    for n in sorted(g.nodes):
        lat, lon = pos(g, n)
        for z in zones:
            b = z["bounds"]
            if b["south"] <= lat < b["north"] and b["west"] <= lon < b["east"]:
                out[z["id"]].append(n)
                break
    return out


def zone_of(p: LatLon, zones: list[dict[str, Any]]) -> str:
    """Zone containing p, else the zone with the nearest centroid."""
    for z in zones:
        b = z["bounds"]
        if b["south"] <= p[0] <= b["north"] and b["west"] <= p[1] <= b["east"]:
            return z["id"]
    return min(zones, key=lambda z: haversine_m(p, (z["centroid"]["lat"], z["centroid"]["lon"])))["id"]
