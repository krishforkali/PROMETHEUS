"""Download OSM roads + hospitals around Nagpur and write deterministic seed data.

Real OSM data is the default. If Overpass is unreachable after retries, a
synthetic grid network (flagged "simulated") is generated so the pipeline never blocks.

Usage:  python sim/build_dataset.py [--out sim/data] [--offline]
"""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path
from typing import Any, Callable, TypeVar

import networkx as nx
import osmnx as ox

from generate import (
    CENTER,
    RADIUS_M,
    SEED,
    bbox_around,
    make_fleet,
    make_synthetic_hospitals,
    make_synthetic_roads,
    make_zones,
)
from hospitals import add_bed_capacity, select_hospitals

DEFAULT_OUT = Path(__file__).parent / "data"
OVERPASS_URL = "https://maps.mail.ru/osm/tools/overpass/api"
ROADS_TIMEOUT_S = 90
HOSPITALS_TIMEOUT_S = 60
RETRIES = 2  # retries after the first attempt
RETRY_DELAY_S = 5.0
MAJOR_ROADS_FILTER = '["highway"~"motorway|trunk|primary|secondary|tertiary"]'

T = TypeVar("T")


def configure_osmnx() -> None:
    ox.settings.overpass_url = OVERPASS_URL
    ox.settings.use_cache = True
    ox.settings.log_console = True  # osmnx prints each request it makes


def with_retries(
    fn: Callable[[], T], label: str, retries: int = RETRIES, delay_s: float = RETRY_DELAY_S
) -> T:
    """Call fn, retrying with linear backoff and printing progress; re-raises the last error."""
    attempts = retries + 1
    for attempt in range(1, attempts + 1):
        start = time.monotonic()
        print(f"[{label}] attempt {attempt}/{attempts} ...", flush=True)
        try:
            result = fn()
            print(f"[{label}] done in {time.monotonic() - start:.1f}s", flush=True)
            return result
        except Exception as exc:  # network/Overpass errors come in many types
            print(f"[{label}] failed after {time.monotonic() - start:.1f}s: {type(exc).__name__}: {exc}", flush=True)
            if attempt == attempts:
                raise
            time.sleep(delay_s * attempt)
    raise AssertionError("unreachable")


def sort_list_attrs(graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """osmnx merges multi-valued tags in set (hash) order; sort them so output is reproducible."""
    for _, _, data in graph.edges(data=True):
        for key, value in data.items():
            if isinstance(value, list):
                data[key] = sorted(value, key=str)
    return graph


def download_roads(center: tuple[float, float], radius_m: int) -> nx.MultiDiGraph:
    ox.settings.requests_timeout = ROADS_TIMEOUT_S
    graph = ox.graph_from_point(
        center, dist=radius_m, dist_type="bbox", custom_filter=MAJOR_ROADS_FILTER, simplify=True
    )
    return sort_list_attrs(graph)


def download_hospitals(center: tuple[float, float], radius_m: int, graph: nx.MultiDiGraph) -> list[dict[str, Any]]:
    ox.settings.requests_timeout = HOSPITALS_TIMEOUT_S
    gdf = ox.features_from_point(center, tags={"amenity": "hospital"}, dist=radius_m)
    areas = gdf.geometry.to_crs(gdf.estimate_utm_crs()).area
    raw: list[dict[str, Any]] = []
    for (osm_type, osm_id), row in gdf.iterrows():
        pt = row.geometry.centroid
        raw.append(
            {
                "id": f"{osm_type}/{osm_id}",
                "name": _attr_str(row.get("name")),
                "lat": pt.y,
                "lon": pt.x,
                "amenity": _attr_str(row.get("amenity")),
                "healthcare": _attr_str(row.get("healthcare")),
                "emergency": _attr_str(row.get("emergency")),
                "beds": _attr_str(row.get("beds")),
                "area_m2": round(float(areas.loc[(osm_type, osm_id)]), 1),
            }
        )
    selected = select_hospitals(raw)
    print(f"  {len(raw)} raw OSM hospitals -> {len(selected)} after filtering")
    nodes = ox.distance.nearest_nodes(graph, [h["lon"] for h in selected], [h["lat"] for h in selected])
    return [
        {
            "id": h["id"],
            "name": h["name"],
            "lat": h["lat"],
            "lon": h["lon"],
            "node": int(n),
            "emergency": h["emergency"] == "yes",
            "area_m2": h["area_m2"],
            "source": "osm",
            "simulated": False,
        }
        for h, n in zip(selected, nodes)
    ]


def _attr_str(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return ",".join(map(str, value))
    return None


def roads_to_geojson(graph: nx.MultiDiGraph, simulated: bool) -> dict[str, Any]:
    _, edges = ox.graph_to_gdfs(graph, nodes=True, edges=True)
    features = []
    for (u, v, k), row in edges.iterrows():
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": [[x, y] for x, y in row.geometry.coords]},
                "properties": {
                    "u": int(u),
                    "v": int(v),
                    "key": int(k),
                    "length_m": round(float(row["length"]), 1),
                    "highway": _attr_str(row.get("highway")),
                    "name": _attr_str(row.get("name")),
                    "bridge": row.get("bridge") in (True, "yes", "True"),
                    "simulated": simulated,
                },
            }
        )
    features.sort(key=lambda f: (f["properties"]["u"], f["properties"]["v"], f["properties"]["key"]))
    return {"type": "FeatureCollection", "features": features}


def depot_candidates(graph: nx.MultiDiGraph, hospitals: list[dict[str, Any]], seed: int) -> list[dict[str, Any]]:
    """Depots: hospitals if any, else a seeded sample of road nodes."""
    if hospitals:
        return [{"lat": h["lat"], "lon": h["lon"], "node": h["node"]} for h in hospitals]
    nodes = sorted(graph.nodes)
    picks = random.Random(seed).sample(nodes, k=min(8, len(nodes)))
    return [{"lat": graph.nodes[n]["y"], "lon": graph.nodes[n]["x"], "node": int(n)} for n in picks]


def fetch_network(seed: int, offline: bool) -> tuple[nx.MultiDiGraph, list[dict[str, Any]], dict[str, str]]:
    """Real OSM roads + hospitals, falling back to synthetic data per layer."""
    bbox = bbox_around(CENTER, RADIUS_M)
    sources = {"roads": "synthetic", "hospitals": "synthetic"}
    graph: nx.MultiDiGraph | None = None
    if not offline:
        configure_osmnx()
        print(f"Downloading major roads from {OVERPASS_URL} (timeout {ROADS_TIMEOUT_S}s) ...")
        try:
            graph = with_retries(lambda: download_roads(CENTER, RADIUS_M), "roads")
            sources["roads"] = "osm"
        except Exception:
            print("  Overpass unavailable - falling back to SIMULATED synthetic road grid")
    if graph is None:
        graph = make_synthetic_roads(bbox, seed=seed)
    print(f"  {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges ({sources['roads']})")

    hospitals: list[dict[str, Any]] | None = None
    if sources["roads"] == "osm":
        print(f"Downloading hospitals (timeout {HOSPITALS_TIMEOUT_S}s) ...")
        try:
            hospitals = with_retries(lambda: download_hospitals(CENTER, RADIUS_M, graph), "hospitals")
            sources["hospitals"] = "osm"
        except Exception:
            print("  Overpass unavailable - falling back to SIMULATED hospitals")
    if hospitals is None:
        hospitals = make_synthetic_hospitals(graph, seed=seed)
    hospitals = add_bed_capacity(hospitals, seed=seed)
    print(f"  {len(hospitals)} hospitals ({sources['hospitals']})")
    return graph, hospitals, sources


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")


def build(out: Path, seed: int = SEED, offline: bool = False) -> dict[str, str]:
    out.mkdir(parents=True, exist_ok=True)
    bbox = bbox_around(CENTER, RADIUS_M)
    graph, hospitals, sources = fetch_network(seed, offline)

    zones = make_zones(bbox, seed=seed)
    fleet = make_fleet(depot_candidates(graph, hospitals, seed), seed=seed)

    graph.graph.pop("created_date", None)  # timestamp would make the file differ every run
    ox.save_graphml(graph, out / "roads.graphml")
    write_json(out / "roads.geojson", roads_to_geojson(graph, simulated=sources["roads"] != "osm"))
    write_json(out / "hospitals.json", hospitals)
    write_json(out / "zones.json", zones)
    write_json(out / "fleet.json", fleet)
    write_json(
        out / "meta.json",
        {
            "seed": seed,
            "center": {"lat": CENTER[0], "lon": CENTER[1]},
            "radius_m": RADIUS_M,
            "bbox": vars(bbox),
            "sources": sources,
            "counts": {
                "nodes": graph.number_of_nodes(),
                "edges": graph.number_of_edges(),
                "hospitals": len(hospitals),
                "zones": len(zones),
                "fleet": len(fleet),
            },
            "notes": "Zone attributes and fleet are simulated. Roads/hospitals are OSM unless sources says synthetic.",
        },
    )
    print(f"Wrote dataset to {out}")
    return sources


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--offline", action="store_true", help="skip Overpass and use the synthetic network")
    args = parser.parse_args()
    build(args.out, args.seed, args.offline)
