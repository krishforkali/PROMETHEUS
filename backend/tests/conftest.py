import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app  # noqa: E402

FIXTURE = {
    "zones.json": [{"id": "Z01", "population": 1000, "elevation_m": 300.0, "river_distance_m": 50.0, "simulated": True}],
    "fleet.json": [{"id": "AMB-01", "type": "ambulance", "capacity": 2, "speed_kmh": 40.0, "simulated": True}],
    "hospitals.json": [{"id": "node/1", "name": "Test Hospital", "lat": 21.1, "lon": 79.1, "node": 1, "source": "osm"}],
    "roads.geojson": {"type": "FeatureCollection", "features": []},
}


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    for name, data in FIXTURE.items():
        (tmp_path / name).write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setenv("PROMETHEUS_DATA_DIR", str(tmp_path))
    return TestClient(app)


@pytest.fixture
def empty_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("PROMETHEUS_DATA_DIR", str(tmp_path))
    return TestClient(app)
