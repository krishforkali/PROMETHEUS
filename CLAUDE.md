# Project: Disaster impact forecasting + rescue dispatch (PROMETHEUS DM-01)

## Goal
Real-time crisis platform: forecast infrastructure damage and casualties,
then optimise multi-agency dispatch (ambulances, NDRF boats, drones, ration trucks)
and re-optimise live when constraints change.

## Stack
Backend: FastAPI, OR-Tools, NetworkX, osmnx (OSM), WebSocket
Frontend: React + TypeScript + Tailwind + MapLibre GL
Data: simulated flood scenario for a Nagpur-area region; real OSM roads/hospitals.
All simulated data must be labelled "simulated" in the UI.

## Rules
- Build step by step; run and test before moving on
- Deterministic seed data in /sim so demos are repeatable
- Every optimisation result must include: assignments, routes, people reached,
  avg response time, and a nearest-first baseline for comparison
- Keep functions small, typed, and covered by pytest
- Do not add features outside the current step

## Core model
Zones (population, elevation, hazard) -> risk/casualty forecast
Road graph (NetworkX) with failure probabilities and blocked flags
Fleet: types (ambulance, boat, drone, truck), depot, capacity, speed, terrain
Incidents (SOS): location, type, severity, source (dashboard/app/ivr/sms)
Optimiser: OR-Tools VRP, per-vehicle-type travel-time matrices,
capacity + time dimensions, penalties for dropped stops weighted by priority