"""Load the seed dataset produced by sim/build_dataset.py."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "sim" / "data"


def data_dir() -> Path:
    return Path(os.environ.get("PROMETHEUS_DATA_DIR", DEFAULT_DATA_DIR))


@lru_cache(maxsize=None)
def _load(directory: str, name: str) -> Any:
    path = Path(directory) / name
    if not path.exists():
        raise FileNotFoundError(f"{path} missing - run `python sim/build_dataset.py` first")
    return json.loads(path.read_text(encoding="utf-8"))


def load(name: str) -> Any:
    return _load(str(data_dir()), name)
