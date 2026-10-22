from collections import Counter

import pytest
from fastapi.testclient import TestClient

from app.data import DEFAULT_DATA_DIR
from app.main import app

from .conftest import FIXTURE


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


@pytest.mark.parametrize(
    "path,name",
    [("/zones", "zones.json"), ("/fleet", "fleet.json"), ("/hospitals", "hospitals.json"), ("/roads", "roads.geojson")],
)
def test_data_endpoints_serve_files(client: TestClient, path: str, name: str) -> None:
    r = client.get(path)
    assert r.status_code == 200
    assert r.json() == FIXTURE[name]


def test_missing_data_returns_503(empty_client: TestClient) -> None:
    r = empty_client.get("/zones")
    assert r.status_code == 503
    assert "build_dataset" in r.json()["detail"]


@pytest.mark.skipif(not (DEFAULT_DATA_DIR / "meta.json").exists(), reason="real dataset not built")
def test_real_dataset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PROMETHEUS_DATA_DIR", raising=False)
    c = TestClient(app)
    zones = c.get("/zones").json()
    fleet = c.get("/fleet").json()
    roads = c.get("/roads").json()
    hospitals = c.get("/hospitals").json()
    assert len(zones) == 12 and all(z["simulated"] for z in zones)
    assert Counter(v["type"] for v in fleet) == {"ambulance": 6, "boat": 3, "drone": 2, "truck": 3}
    assert roads["type"] == "FeatureCollection" and len(roads["features"]) > 100
    assert isinstance(hospitals, list)
