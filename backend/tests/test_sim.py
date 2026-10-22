import json
import sys
from pathlib import Path
from typing import Any

import pytest

from app.dispatch import Incident, eligible_types
from app.engine import Simulation
from app.forecast import casualties, cut_off_zones, risk
from app.network import edge_key, without_edges
from app.runner import DEFAULT_SCENARIO, new_simulation

SCENARIO: dict[str, Any] = json.loads(DEFAULT_SCENARIO.read_text(encoding="utf-8"))
TARGET = SCENARIO["failure_points"][0]["isolates_zone"]


@pytest.fixture(autouse=True)
def real_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PROMETHEUS_DATA_DIR", raising=False)


@pytest.fixture
def sim() -> Simulation:
    return new_simulation()


def fail_points(s: Simulation, ids: list[str]) -> None:
    for fp in ids:
        s.apply_manual({"type": "block_road", "failure_point": fp})


# ---- forecast -----------------------------------------------------------


def test_risk_formula() -> None:
    assert risk(0, 0.0, 100) == 0
    assert risk(200, 0.0, 0) == 1.0  # rain saturates
    assert risk(50, 0.0, 500) > risk(50, 0.5, 500) > risk(50, 0.5, 2000)
    assert risk(80, 0.2, 500) > risk(40, 0.2, 500)


def test_casualty_band_ordered() -> None:
    c = casualties(100_000, 0.5, 0.004)
    assert c == {"low": 100, "expected": 200, "high": 360}


def test_terrain_rules() -> None:
    inc = Incident("I", 0, 0, 1, "Z01", 3, 10, "medical")
    sup = Incident("S", 0, 0, 1, "Z01", 3, 10, "supplies")
    assert eligible_types(inc, set(), set()) == {"ambulance"}
    assert eligible_types(sup, set(), set()) == {"truck"}
    assert eligible_types(inc, {"Z01"}, set()) == {"boat"}
    assert eligible_types(inc, set(), {"Z01"}) == {"drone"}
    assert eligible_types(inc, {"Z01"}, {"Z01"}) == {"drone", "boat"}


# ---- scenario -----------------------------------------------------------


def test_scenario_is_reproducible_and_flagged() -> None:
    sys.path.insert(0, str(DEFAULT_SCENARIO.parent))
    from build_scenario import build

    assert build() == SCENARIO
    assert SCENARIO["simulated"] is True
    assert len(SCENARIO["hospitals"]) == 7 and len(SCENARIO["failure_points"]) == 4


def test_failure_points_jointly_cut_off_target_zone(sim: Simulation) -> None:
    hospital_nodes = [h["node"] for h in sim.hospitals.values()]
    edges: list[tuple[int, int]] = []
    for k, fp in enumerate(SCENARIO["failure_points"], 1):
        edges += [edge_key(*e) for e in fp["edges"]]
        cut = cut_off_zones(without_edges(sim.graph, edges), sim.zone_nodes, hospital_nodes)
        assert (TARGET in cut) == (k == len(SCENARIO["failure_points"]))


# ---- engine -------------------------------------------------------------


def test_determinism() -> None:
    a, b = new_simulation(), new_simulation()
    for t in (450, 1300, 2500, 3600):
        a.run_until(t)
        b.run_until(t)
    assert json.dumps(a.state(), sort_keys=True) == json.dumps(b.state(), sort_keys=True)


def test_determinism_independent_of_tick_size() -> None:
    coarse, fine = new_simulation(), new_simulation()
    coarse.run_until(3600)
    for _ in range(120):
        fine.step(30)
    assert coarse.metrics() == fine.metrics()


def test_cascade_cuts_off_zone_and_switches_to_drones(sim: Simulation) -> None:
    sim.run_until(2399)
    assert TARGET not in sim.cut_off
    sim.run_until(2400)  # last failure point fails
    assert TARGET in sim.cut_off
    zone = next(z for z in sim.state()["zones"] if z["id"] == TARGET)
    assert zone["cut_off"] is True
    sim.run_until(3000)  # SOS wave with calls from the cut-off zone
    vehicle_type = {v["id"]: v["type"] for v in sim.vehicles.values()}
    stranded = [a for a in sim.plan["assignments"] if sim.incidents[a["incident"]]["zone"] == TARGET]
    assert stranded, "cut-off zone incidents should still be served"
    assert all(vehicle_type[a["vehicle"]] in ("drone", "boat") for a in stranded)


def test_flood_zone_incidents_use_boats(sim: Simulation) -> None:
    sim.run_until(600)
    vehicle_type = {v["id"]: v["type"] for v in sim.vehicles.values()}
    flooded = [a for a in sim.plan["assignments"] if sim.incidents[a["incident"]]["zone"] in sim.flooded]
    assert flooded and all(vehicle_type[a["vehicle"]] == "boat" for a in flooded)


def test_plan_reports_metrics_and_beats_or_matches_baseline(sim: Simulation) -> None:
    sim.run_until(1800)
    plan = sim.plan
    for key in ("assignments", "routes", "metrics", "baseline", "improvement_pct"):
        assert key in plan
    assert {"people_reached", "avg_response_s", "cost"} <= plan["metrics"].keys()
    assert plan["baseline"]["method"] == "nearest-first"
    assert plan["metrics"]["cost"] <= plan["baseline"]["cost"]
    assert plan["improvement_pct"]["cost"] >= 0
    for route in plan["routes"]:
        assert all(len(leg["path"]) >= 2 for leg in route["legs"])


def test_ambulances_end_at_hospital_with_beds(sim: Simulation) -> None:
    sim.run_until(600)
    amb_routes = [r for r in sim.plan["routes"] if r["type"] == "ambulance"]
    assert amb_routes
    for r in amb_routes:
        assert r["legs"][-1]["to"]["kind"] == "hospital"
        assert sim.hospitals[r["legs"][-1]["to"]["id"]]["beds_available"] > 0


def test_replan_on_new_sos(sim: Simulation) -> None:
    sim.run_until(100)
    version = sim.plan_version
    z = next(z for z in sim.zones if z["id"] not in sim.flooded and z["id"] not in sim.cut_off)
    entry = sim.apply_manual(
        {"type": "add_sos", "lat": z["centroid"]["lat"], "lon": z["centroid"]["lon"], "severity": 5, "people": 8}
    )
    assert sim.plan_version == version + 1
    new_id = entry["message"].split()[2].split("@")[0]
    assert new_id in {a["incident"] for a in sim.plan["assignments"]}


def test_replan_on_vehicle_lost(sim: Simulation) -> None:
    sim.run_until(700)
    busy = sim.plan["assignments"][0]["vehicle"]
    version = sim.plan_version
    sim.apply_manual({"type": "remove_vehicle", "vehicle": busy})
    assert sim.plan_version == version + 1
    assert sim.vehicles[busy]["status"] == "lost"
    assert busy not in {a["vehicle"] for a in sim.plan["assignments"]}


def test_replan_on_road_block(sim: Simulation) -> None:
    sim.run_until(700)
    version = sim.plan_version
    u, v = next(iter(sim.graph.edges))
    sim.apply_manual({"type": "block_road", "u": u, "v": v})
    assert sim.plan_version == version + 1
    assert edge_key(u, v) in sim.blocked


def test_timeline_vehicle_loss_applied(sim: Simulation) -> None:
    sim.run_until(2700)
    assert sim.vehicles["DRO-01"]["status"] == "lost"


def test_full_run_serves_people(sim: Simulation) -> None:
    sim.run_until(3 * 3600)
    m = sim.metrics()
    assert m["served"] > 0 and m["people_reached"] > 0 and m["avg_response_s"] > 0


@pytest.mark.parametrize(
    "event",
    [
        {"type": "remove_vehicle", "vehicle": "NOPE"},
        {"type": "block_road", "failure_point": "FP99"},
        {"type": "add_sos", "lat": 21.14, "lon": 79.09, "severity": 9, "people": 3},
        {"type": "meteor"},
    ],
)
def test_bad_manual_events_rejected(sim: Simulation, event: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        sim.apply_manual(event)


def test_scenario_file_location() -> None:
    assert Path(DEFAULT_SCENARIO).exists()


def test_sos_wave_is_seeded_and_replans() -> None:
    a, b = new_simulation(), new_simulation()
    for s in (a, b):
        s.apply_manual({"type": "add_sos_wave", "count": 4})
    assert [i["lat"] for i in a.incidents.values()] == [i["lat"] for i in b.incidents.values()]
    assert len(a.incidents) == 4 and all(i["source"] == "dashboard" for i in a.incidents.values())
    s = new_simulation()
    s.apply_manual({"type": "add_sos_wave", "count": 3, "zone": "Z02"})
    assert {i["zone"] for i in s.incidents.values()} == {"Z02"}
    with pytest.raises(ValueError):
        s.apply_manual({"type": "add_sos_wave", "count": 99})


def test_state_has_dashboard_fields(sim: Simulation) -> None:
    sim.run_until(700)
    st = sim.state()
    assert st["metrics"]["people_at_risk"] > 0
    assert {fp["label"] for fp in st["failure_points"]} == {"Underpass A", "Underpass B", "Underpass C", "Underpass D"}
    moving = [v for v in st["vehicles"] if v["status"] == "en_route"]
    assert moving and all(v["route"][0] == (v["lat"], v["lon"]) and len(v["route"]) >= 2 for v in moving)
    assert next(v for v in st["vehicles"] if v["id"] == "DRO-02")["label"] == "Drone 2"


def test_log_names_things_readably(sim: Simulation) -> None:
    sim.run_until(2700)
    messages = [e["message"] for e in sim.log]
    assert "Underpass A failed, re-planning" in messages
    assert "Drone 1 lost, re-planning" in messages


def test_cumulative_plan_gain_vs_baseline(sim: Simulation) -> None:
    assert sim.metrics()["plan_gain_pct"] is None
    sim.run_until(3600)
    m = sim.metrics()
    assert m["plans_compared"] > 5
    assert m["plan_gain_pct"] > 0  # waves exceed fleet capacity, so optimisation pays off


# ---- operator approval and explanations ----------------------------------


def test_manual_approval_holds_clock_until_approved(sim: Simulation) -> None:
    sim.run_until(700)
    active = sim.plan["version"]
    sim.set_auto_approve(False)
    sim.apply_manual({"type": "add_sos_wave", "count": 2})
    assert sim.proposal is not None and sim.plan["version"] == active
    new_ids = sorted(i["id"] for i in sim.incidents.values() if i["created_s"] == 700)
    assert set(new_ids) <= set(sim.proposal["changes"]["added"]) | set(sim.proposal["dropped"])
    held_at = sim.time_s
    sim.run_until(held_at + 600)
    assert sim.time_s == held_at  # clock held while the operator decides
    sim.approve()
    assert sim.proposal is None and sim.plan["version"] > active
    with pytest.raises(ValueError):
        sim.approve()
    sim.run_until(held_at + 600)
    # Clock resumes; it either reaches the target or holds at the next re-plan that changes something.
    assert sim.time_s > held_at
    if sim.time_s < held_at + 600:
        c = sim.proposal["changes"]
        assert c["added"] or c["reassigned"] or c["unassigned"]


def test_newer_proposal_replaces_pending_one(sim: Simulation) -> None:
    sim.run_until(700)
    sim.set_auto_approve(False)
    sim.apply_manual({"type": "add_sos_wave", "count": 2})
    first = sim.proposal["version"]
    busy = next(a["vehicle"] for a in sim.proposal["assignments"])
    sim.apply_manual({"type": "remove_vehicle", "vehicle": busy})
    assert sim.proposal["version"] == first + 1
    assert busy not in {a["vehicle"] for a in sim.proposal["assignments"]}


def test_enabling_auto_approve_applies_pending(sim: Simulation) -> None:
    sim.set_auto_approve(False)
    sim.apply_manual({"type": "add_sos_wave", "count": 1})
    assert sim.proposal is not None
    sim.set_auto_approve(True)
    assert sim.proposal is None and sim.plan["assignments"]


def test_plan_changes_report_reassignments(sim: Simulation) -> None:
    sim.run_until(700)
    busy = sim.plan["assignments"][0]
    sim.apply_manual({"type": "remove_vehicle", "vehicle": busy["vehicle"]})
    c = sim.plan["changes"]
    moved = {r["incident"]: r for r in c["reassigned"]}
    assert busy["incident"] in moved or busy["incident"] in c["unassigned"]
    if busy["incident"] in moved:
        assert moved[busy["incident"]]["from"] == busy["vehicle"]


def test_every_assignment_explains_itself(sim: Simulation) -> None:
    sim.run_until(3000)  # Z11 cut off by now
    types = {v["id"]: v["type"] for v in sim.vehicles.values()}
    for a in sim.plan["assignments"]:
        w = a["why"]
        assert w["priority"] == sim.incidents[a["incident"]]["severity"] * sim.incidents[a["incident"]]["people"]
        assert 1 <= w["rank"] <= w["of"] and w["travel_s"] >= 0 and w["distance_m"] >= 0
        assert w["nearest"]["vehicle"] in types and types[w["nearest"]["vehicle"]] == types[a["vehicle"]]
        if w["nearest"]["vehicle"] == a["vehicle"]:
            assert w["nearest"]["busy_with"] == []
        if types[a["vehicle"]] == "ambulance":
            assert w["hospital"]["beds_free"] > 0
        if sim.incidents[a["incident"]]["zone"] == TARGET:
            assert "cut off" in w["rule"]


def test_no_change_replan_does_not_hold_clock(sim: Simulation) -> None:
    sim.run_until(700)
    sim.set_auto_approve(False)
    rain = {"type": "rain", "mm_per_hr": sim.rain_mm_hr}
    sim._apply(rain, source="manual")  # may reshuffle: vehicles have moved since t=600
    if sim.proposal:
        sim.approve()
    version = sim.plan["version"]
    sim._apply(rain, source="manual")  # same instant, same inputs: nothing changes
    assert sim.proposal is None
    assert sim.plan["version"] == version + 1
    assert sim.plan["changes"]["unchanged"] == len(sim.plan["assignments"])


def test_simultaneous_arrivals_replan_once(sim: Simulation) -> None:
    sim.run_until(700)
    sim.set_auto_approve(False)
    # Two vehicles finishing at the same instant must produce a single re-plan.
    idle = [v for v in sim.vehicles.values() if v["status"] == "en_route"][:2]
    assert len(idle) == 2
    t = sim.time_s + 5
    z = sim.zones[0]
    sim._add_incident({"lat": z["centroid"]["lat"], "lon": z["centroid"]["lon"], "severity": 3, "people": 5})
    for v in idle:
        v["legs"] = [{**v["legs"][0], "depart_s": sim.time_s, "arrive_s": t}]
    version = sim.plan_version
    sim.run_until(t)
    assert sim.plan_version == version + 1
    latest = sim.proposal or sim.plan
    assert all(v["label"] in latest["reason"] for v in idle)
