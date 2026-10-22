"""Download OSM roads + hospitals around Nagpur and write deterministic seed data.

Usage:  python sim/build_dataset.py [--out sim/data]
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

import networkx as nx
import osmnx as ox

from generate import CENTER, RADIUS_M, SEED, bbox_around, make_fleet, make_zones

DEFAULT_OUT = Path(__file__).parent / "data"


def download_roads(center: tuple[float, float], radius_m: int) -> nx.MultiDiGraph:
    return ox.graph_from_point(center, dist=radius_m, dist_type="bbox", network_type="drive", simplify=True)


def download_hospitals(center: tuple[float, float], radius_m: int, graph: nx.MultiDiGraph) -> list[dict[str, Any]]:
    gdf = ox.features_from_point(center, tags={"amenity": "hospital"}, dist=radius_m)
    hospitals: list[dict[str, Any]] = []
    for (osm_type, osm_id), row in gdf.iterrows():
        pt = row.geometry.centroid
        hospitals.append(
            {
                "id": f"{osm_type}/{osm_id}",
                "name": row.get("name") if isinstance(row.get("name"), str) else "Unnamed hospital",
                "lat": pt.y,
                "lon": pt.x,
                "node": int(ox.distance.nearest_nodes(graph, pt.x, pt.y)),
                "source": "osm",
            }
        )
    return sorted(hospitals, key=lambda h: h["id"])


def roads_to_geojson(graph: nx.MultiDiGraph) -> dict[str, Any]:
    _, edges = ox.graph_to_gdfs(graph, nodes=True, edges=True)
    features = []
    for (u, v, k), row in edges.iterrows():
        hw = row.get("highway")
        name = row.get("name")
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": [[x, y] for x, y in row.geometry.coords]},
                "properties": {
                    "u": int(u),
                    "v": int(v),
                    "key": int(k),
                    "length_m": round(float(row["length"]), 1),
                    "highway": hw if isinstance(hw, str) else ",".join(hw) if isinstance(hw, list) else None,
                    "name": name if isinstance(name, str) else None,
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


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=1), encoding="utf-8")


def build(out: Path, seed: int = SEED) -> None:
    out.mkdir(parents=True, exist_ok=True)
    bbox = bbox_around(CENTER, RADIUS_M)

    print("Downloading road graph...")
    graph = download_roads(CENTER, RADIUS_M)
    print(f"  {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")
    print("Downloading hospitals...")
    hospitals = download_hospitals(CENTER, RADIUS_M, graph)
    print(f"  {len(hospitals)} hospitals")

    zones = make_zones(bbox, seed=seed)
    fleet = make_fleet(depot_candidates(graph, hospitals, seed), seed=seed)

    ox.save_graphml(graph, out / "roads.graphml")
    write_json(out / "roads.geojson", roads_to_geojson(graph))
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
            "counts": {
                "nodes": graph.number_of_nodes(),
                "edges": graph.number_of_edges(),
                "hospitals": len(hospitals),
                "zones": len(zones),
                "fleet": len(fleet),
            },
            "notes": "Roads and hospitals from OpenStreetMap; zones attributes and fleet are simulated.",
        },
    )
    print(f"Wrote dataset to {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args()
    build(args.out, args.seed)
