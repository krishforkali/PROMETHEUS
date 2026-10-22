from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException

from app.data import load

app = FastAPI(title="PROMETHEUS DM-01")


def _get(name: str) -> Any:
    try:
        return load(name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/zones")
def zones() -> list[dict[str, Any]]:
    return _get("zones.json")


@app.get("/fleet")
def fleet() -> list[dict[str, Any]]:
    return _get("fleet.json")


@app.get("/hospitals")
def hospitals() -> list[dict[str, Any]]:
    return _get("hospitals.json")


@app.get("/roads")
def roads() -> dict[str, Any]:
    return _get("roads.geojson")
