import json
from pathlib import Path

import pytest

import build_dataset


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(build_dataset.time, "sleep", lambda _s: None)


def test_with_retries_succeeds_after_failures() -> None:
    calls = []

    def flaky() -> str:
        calls.append(1)
        if len(calls) < 3:
            raise ConnectionError("down")
        return "ok"

    assert build_dataset.with_retries(flaky, "t", retries=2) == "ok"
    assert len(calls) == 3


def test_with_retries_reraises_last_error() -> None:
    def always_fail() -> None:
        raise ConnectionError("down")

    with pytest.raises(ConnectionError):
        build_dataset.with_retries(always_fail, "t", retries=1)


def test_build_falls_back_to_synthetic_when_overpass_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args: object) -> None:
        raise ConnectionError("overpass down")

    monkeypatch.setattr(build_dataset, "download_roads", fail)
    sources = build_dataset.build(tmp_path)

    assert sources == {"roads": "synthetic", "hospitals": "synthetic"}
    for name in ["roads.graphml", "roads.geojson", "hospitals.json", "zones.json", "fleet.json", "meta.json"]:
        assert (tmp_path / name).exists()
    roads = json.loads((tmp_path / "roads.geojson").read_text())
    assert roads["features"] and all(f["properties"]["simulated"] for f in roads["features"])
    assert sum(f["properties"]["bridge"] for f in roads["features"]) == 8  # 4 bridges, both directions
    hospitals = json.loads((tmp_path / "hospitals.json").read_text())
    assert all(h["simulated"] for h in hospitals)
    meta = json.loads((tmp_path / "meta.json").read_text())
    assert meta["sources"]["roads"] == "synthetic"


def test_offline_flag_skips_download(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def must_not_call(*_args: object) -> None:
        raise AssertionError("download attempted")

    monkeypatch.setattr(build_dataset, "download_roads", must_not_call)
    assert build_dataset.build(tmp_path, offline=True)["roads"] == "synthetic"
