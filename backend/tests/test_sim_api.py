from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.runner import SimRunner


@pytest.fixture
def sim_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.delenv("PROMETHEUS_DATA_DIR", raising=False)
    app.state.runner = SimRunner(tick_real_s=0.02)
    with TestClient(app) as c:
        yield c
    app.state.runner.pause()
    app.state.runner = None


def test_state_shape(sim_client: TestClient) -> None:
    s = sim_client.get("/state").json()
    assert s["simulated"] is True
    for key in ("zones", "failure_points", "hospitals", "vehicles", "incidents", "plan", "metrics", "clock"):
        assert key in s
    assert len(s["zones"]) == 12 and len(s["hospitals"]) == 7


def test_start_pause_speed(sim_client: TestClient) -> None:
    assert sim_client.post("/sim/speed", json={"speed": 120}).json()["speed"] == 120
    assert sim_client.post("/sim/speed", json={"speed": 0}).status_code == 400
    assert sim_client.post("/sim/start").json()["running"] is True
    assert sim_client.post("/sim/pause").json()["running"] is False


def test_manual_events_trigger_replan(sim_client: TestClient) -> None:
    v0 = sim_client.get("/state").json()["plan"]["version"]
    r = sim_client.post(
        "/sim/event", json={"type": "add_sos", "lat": 21.13, "lon": 79.07, "severity": 4, "people": 6}
    )
    assert r.status_code == 200 and r.json()["plan_version"] == v0 + 1
    r = sim_client.post("/sim/event", json={"type": "block_road", "failure_point": "FP1"})
    assert r.status_code == 200 and r.json()["plan_version"] == v0 + 2
    r = sim_client.post("/sim/event", json={"type": "remove_vehicle", "vehicle": "AMB-01"})
    assert r.status_code == 200
    vehicles = {v["id"]: v for v in sim_client.get("/state").json()["vehicles"]}
    assert vehicles["AMB-01"]["status"] == "lost"


def test_bad_events_400(sim_client: TestClient) -> None:
    assert sim_client.post("/sim/event", json={"type": "add_sos", "lat": 21.1}).status_code == 400
    assert sim_client.post("/sim/event", json={"type": "remove_vehicle", "vehicle": "X"}).status_code == 400
    assert sim_client.post("/sim/event", json={"type": "nuke"}).status_code == 422


def test_websocket_pushes_state_each_tick(sim_client: TestClient) -> None:
    with sim_client.websocket_connect("/ws") as ws:
        first = ws.receive_json()
        assert first["time_s"] == 0
        sim_client.post("/sim/start")
        tick = ws.receive_json()
        assert tick["time_s"] > first["time_s"] and tick["clock"]["running"] is True
        sim_client.post("/sim/pause")


def test_reset_restarts_scenario(sim_client: TestClient) -> None:
    sim_client.post("/sim/event", json={"type": "add_sos_wave", "count": 3})
    assert len(sim_client.get("/state").json()["incidents"]) == 3
    r = sim_client.post("/sim/reset")
    assert r.status_code == 200 and r.json()["running"] is False
    s = sim_client.get("/state").json()
    assert s["time_s"] == 0 and s["incidents"] == []
