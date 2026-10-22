from typing import Any

from hospitals import add_bed_capacity, dedupe, is_real_hospital, select_hospitals


def rec(id: str, name: str | None = "City Hospital", lat: float = 21.14, lon: float = 79.08, **tags: Any) -> dict[str, Any]:
    return {"id": id, "name": name, "lat": lat, "lon": lon, "amenity": "hospital", "area_m2": 0.0, **tags}


def test_filters_non_hospitals_and_unnamed() -> None:
    assert is_real_hospital(rec("n/1"))
    assert not is_real_hospital(rec("n/2", amenity="clinic"))
    assert not is_real_hospital(rec("n/3", healthcare="nursing_home"))
    assert not is_real_hospital(rec("n/4", name="Sharma Clinic"))
    assert not is_real_hospital(rec("n/5", name="Shree Nursing Home"))
    assert not is_real_hospital(rec("n/6", name=None))
    assert not is_real_hospital(rec("n/7", name="  "))


def test_dedupe_point_vs_outline_keeps_outline() -> None:
    point = rec("node/1", name="Mayo Hospital")
    outline = rec("way/2", name="mayo  hospital", lat=21.1404, area_m2=5000.0)  # ~45 m away
    far = rec("node/3", name="Mayo Hospital", lat=21.15)  # ~1.1 km away: distinct
    kept = dedupe([point, outline, far])
    assert {r["id"] for r in kept} == {"way/2", "node/3"}


def test_select_ranks_emergency_then_beds_then_area() -> None:
    records = [rec(f"node/{i}", name=f"Hospital {i}", lat=21.10 + i * 0.01, area_m2=float(i)) for i in range(20)]
    records.append(rec("node/er", name="ER Hospital", emergency="yes"))
    records.append(rec("node/beds", name="Beds Hospital", beds="120"))
    top = select_hospitals(records, limit=15)
    ids = {r["id"] for r in top}
    assert len(top) == 15
    assert {"node/er", "node/beds"} <= ids
    assert {f"node/{i}" for i in range(7, 20)} <= ids  # 13 largest by area fill the rest
    assert [r["id"] for r in top] == sorted(ids)


def test_bed_capacity_deterministic_and_simulated() -> None:
    hs = [rec("n/1", emergency="yes"), rec("n/2"), rec("n/3", emergency=True)]
    a, b = add_bed_capacity(hs, seed=1), add_bed_capacity(hs, seed=1)
    assert a == b
    for h in a:
        cap = h["capacity"]
        assert cap["simulated"] is True
        assert 0 < cap["beds_available"] <= cap["beds_total"]
    assert a[0]["capacity"]["beds_total"] >= 200 and a[2]["capacity"]["beds_total"] >= 200


def test_bed_capacity_uses_real_beds_tag() -> None:
    [h] = add_bed_capacity([rec("n/1", beds="250")])
    assert h["capacity"]["beds_total"] == 250 and h["capacity"]["simulated"] is False
