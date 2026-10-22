"""Clean, rank and enrich hospital records. Pure functions, no network."""

from __future__ import annotations

import random
import re
from typing import Any

from generate import SEED, haversine_m

MAX_HOSPITALS = 15
DUPLICATE_RADIUS_M = 100.0
EXCLUDED_HEALTHCARE = {"clinic", "doctor", "doctors", "pharmacy", "nursing_home", "dentist"}
# OSM in Nagpur often tags small facilities as amenity=hospital; catch them by name.
EXCLUDED_NAME = re.compile(r"\b(clinic|nursing\s*home|dental|pharmacy|medical\s*store|chemist)\b", re.I)


def _norm_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.casefold()).strip()


def is_real_hospital(rec: dict[str, Any]) -> bool:
    name = rec.get("name")
    return (
        rec.get("amenity") == "hospital"
        and rec.get("healthcare") not in EXCLUDED_HEALTHCARE
        and isinstance(name, str)
        and bool(name.strip())
        and not EXCLUDED_NAME.search(name)
    )


def significance(rec: dict[str, Any]) -> tuple[bool, bool, float, str]:
    """Sort key (descending): emergency=yes, has beds tag, building area; id breaks ties."""
    return (rec.get("emergency") == "yes", rec.get("beds") is not None, rec.get("area_m2", 0.0), rec["id"])


def dedupe(records: list[dict[str, Any]], radius_m: float = DUPLICATE_RADIUS_M) -> list[dict[str, Any]]:
    """Drop records sharing a normalised name within radius_m, keeping the most significant."""
    kept: list[dict[str, Any]] = []
    for rec in sorted(records, key=significance, reverse=True):
        key = _norm_name(rec["name"])
        if not any(
            _norm_name(k["name"]) == key and haversine_m((k["lat"], k["lon"]), (rec["lat"], rec["lon"])) <= radius_m
            for k in kept
        ):
            kept.append(rec)
    return kept


def select_hospitals(records: list[dict[str, Any]], limit: int = MAX_HOSPITALS) -> list[dict[str, Any]]:
    """Filter, dedupe and keep the `limit` most significant hospitals, sorted by id."""
    unique = dedupe([r for r in records if is_real_hospital(r)])
    top = sorted(unique, key=significance, reverse=True)[:limit]
    return sorted(top, key=lambda r: r["id"])


def add_bed_capacity(hospitals: list[dict[str, Any]], seed: int = SEED) -> list[dict[str, Any]]:
    """Attach simulated bed capacity; emergency hospitals skew larger."""
    rng = random.Random(seed)
    out = []
    for h in hospitals:
        lo, hi = (200, 800) if h.get("emergency") in ("yes", True) else (40, 300)
        tagged = str(h.get("beds", "")).isdigit()
        total = int(h["beds"]) if tagged else rng.randint(lo, hi)
        available = round(total * rng.uniform(0.1, 0.4))
        capacity = {"beds_total": total, "beds_available": available, "simulated": not tagged}
        out.append({**h, "capacity": capacity})
    return out
