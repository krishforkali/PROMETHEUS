from collections import Counter

import pytest

from generate import (
    CENTER,
    RADIUS_M,
    bbox_around,
    distance_to_river_m,
    haversine_m,
    make_fleet,
    make_zones,
)

BBOX = bbox_around(CENTER, RADIUS_M)
DEPOTS = [{"lat": 21.14, "lon": 79.08, "node": 1}, {"lat": 21.15, "lon": 79.09, "node": 2}]


def test_bbox_is_about_10km_square() -> None:
    width = haversine_m((CENTER[0], BBOX.west), (CENTER[0], BBOX.east))
    height = haversine_m((BBOX.south, CENTER[1]), (BBOX.north, CENTER[1]))
    assert width == pytest.approx(10_000, rel=0.01)
    assert height == pytest.approx(10_000, rel=0.01)


def test_twelve_zones_tile_the_bbox() -> None:
    zones = make_zones(BBOX)
    assert len(zones) == 12
    assert len({z["id"] for z in zones}) == 12
    total_area = sum(
        (z["bounds"]["north"] - z["bounds"]["south"]) * (z["bounds"]["east"] - z["bounds"]["west"]) for z in zones
    )
    assert total_area == pytest.approx((BBOX.north - BBOX.south) * (BBOX.east - BBOX.west))


def test_zone_attributes_plausible_and_simulated() -> None:
    for z in make_zones(BBOX):
        assert 15_000 <= z["population"] <= 120_000
        assert 280 <= z["elevation_m"] <= 330
        assert z["river_distance_m"] >= 0
        assert z["simulated"] is True
        assert z["polygon"][0] == z["polygon"][-1]


def test_zones_deterministic_per_seed() -> None:
    assert make_zones(BBOX, seed=7) == make_zones(BBOX, seed=7)
    assert make_zones(BBOX, seed=7) != make_zones(BBOX, seed=8)


def test_fleet_composition() -> None:
    fleet = make_fleet(DEPOTS)
    assert Counter(v["type"] for v in fleet) == {"ambulance": 6, "boat": 3, "drone": 2, "truck": 3}
    assert len({v["id"] for v in fleet}) == len(fleet)
    for v in fleet:
        assert v["capacity"] > 0 and v["speed_kmh"] > 0
        assert v["depot"] in DEPOTS
        assert v["simulated"] is True


def test_fleet_deterministic() -> None:
    assert make_fleet(DEPOTS, seed=3) == make_fleet(DEPOTS, seed=3)


def test_fleet_requires_depots() -> None:
    with pytest.raises(ValueError):
        make_fleet([])


def test_river_distance_zero_on_river() -> None:
    assert distance_to_river_m((21.1530, 79.0700)) == pytest.approx(0, abs=1)
