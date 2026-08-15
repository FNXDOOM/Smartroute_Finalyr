# SmartRouteAI — Architecture Documentation

This folder contains detailed technical documentation for every layer of the SmartRouteAI system.

---

## Documents

| File | What it covers |
|---|---|
| [system-design.md](./system-design.md) | How every component connects — full data flow from passenger request to vehicle dispatch |
| [api-reference.md](./api-reference.md) | Every endpoint — method, path, auth, request body, response shape, status codes |
| [db-schema.md](./db-schema.md) | All 12 database tables — columns, types, constraints, indexes, foreign keys, relationships |
| [algorithms.md](./algorithms.md) | How each AI/optimization algorithm works and where it fits in the pipeline |
| [background-jobs.md](./background-jobs.md) | The 4 background workers — what they do, when they run, what they write |
| [websockets.md](./websockets.md) | Real-time WebSocket channels — connection, authentication, message formats |
| [supabase.md](./supabase.md) | Supabase setup, PostgreSQL migration, Auth, RLS, environment variables, and deployment |

---

## Quick System Overview

```
Passenger App / Driver App / Admin Dashboard
              ↓  HTTP + WebSocket
         FastAPI Backend (Python 3.10)
              ↓
    ┌─────────────────────────────┐
    │  H3 Spatial Partitioning    │  groups ride requests by hex cell
    │  HDBSCAN Clustering         │  finds passenger groups within cells
    │  K-Medoids Stop Selection   │  picks optimal pickup point per group
    │  OSMnx Road Snapping        │  moves pickup point onto nearest road
    │  OR-Tools VRP Solver        │  assigns stop sequences to vehicles
    │  Hungarian Assignment       │  matches idle vehicles to routes
    │  XGBoost Demand Predictor   │  forecasts future ride demand by zone
    └─────────────────────────────┘
              ↓
    Supabase PostgreSQL + PostGIS  (SQLite only for local development)
```

---

## Tech Stack Summary

| Layer | Technology |
|---|---|
| API framework | FastAPI 0.104 |
| ORM | SQLAlchemy 2.0 |
| Schema validation | Pydantic v2 |
| Database (prod) | Supabase PostgreSQL + PostGIS |
| Database (dev) | SQLite only when explicitly configured |
| Auth | Clerk session JWTs verified by FastAPI |
| Spatial indexing | H3 (Uber) resolution 9 |
| Clustering | HDBSCAN |
| Stop placement | scikit-learn-extra K-Medoids |
| Road snapping | OSMnx + NetworkX |
| Route optimization | Google OR-Tools (CVRP) |
| Vehicle assignment | SciPy Hungarian algorithm |
| Demand prediction | XGBoost regressor |
| Real-time | WebSockets via Starlette |
| Frontend | React + Vite + Leaflet + Tailwind |
| Map tiles | OpenStreetMap/CARTO via React Leaflet (no Google Maps key) |
| Address geocoding | Nominatim OpenStreetMap service |
