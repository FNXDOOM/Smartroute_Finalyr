# API Reference

Base URL: `http://localhost:8000`

All protected routes require the header:
```
Authorization: Bearer <jwt_token>
```

Obtain a session token from Clerk and send it as the Bearer token. FastAPI
validates the Clerk signature, issuer, and optional audience.

---

## Auth `/auth`

---

### `GET /auth/me`
Get the application profile for the currently authenticated Clerk user.

**Auth required:** Yes (any role)

**Responses:**
- `200` — User profile
- `401` — Missing or invalid token

---

### `PATCH /auth/me`
Update your own name, email, or phone number.

**Auth required:** Yes (any role)

**Request body (all fields optional):**
```json
{ "name": "New Name", "email": "new@example.com", "phone": "0509876543" }
```

**Responses:**
- `200` — Updated profile
- `400` — Email already taken by another account

---

### `PATCH /auth/users/{user_id}/role`
Change a user's role. Admin only.

**Auth required:** Yes (admin)

**Query param:** `?role=driver` (one of `passenger`, `driver`, `admin`)

**Responses:**
- `200` — Updated user profile
- `400` — Invalid role
- `403` — Not an admin
- `404` — User not found

---

## Rides `/rides`

---

### `POST /rides/request`
Submit a new ride request. Authenticated user becomes the passenger. Always created with `mode="live"`.

**Auth required:** Yes (any role)

**Request body:**
```json
{
  "pickup_lat": 12.9719,
  "pickup_lng": 77.6412,
  "dest_lat": 12.9756,
  "dest_lng": 77.6066,
  "pickup_label": "Indiranagar 100 Feet Rd",
  "destination_label": "MG Road Metro",
  "ride_option_id": "swift-x",
  "ride_option_name": "SwiftX",
  "ride_option_price": "₹12–15"
}
```

| Field | Required | Notes |
|---|---|---|
| pickup_lat / pickup_lng | yes | Range: lat ±90, lng ±180; must be within India (`is_india_location`) |
| dest_lat / dest_lng | yes | Must be within India |
| pickup_label / destination_label | no | Human-readable names |
| ride_option_* | no | Display metadata only, not used in routing |

**Responses:**
- `201` — Ride created with `status: "pending"`, `mode: "live"` and computed `h3_index` (res 9)
- `422` — Coordinates out of range or outside India

---

### `GET /rides/my-rides`
Get all ride requests submitted by the authenticated user.

**Auth required:** Yes (any role)

**Responses:**
- `200` — List of rides, newest first

---

### `GET /rides/{ride_id}`
Get a single ride request by ID.

**Auth required:** Yes
- Passenger can only view their own rides
- Admin can view any ride

**Responses:**
- `200` — Ride details
- `403` — Not your ride (and not admin)
- `404` — Ride not found

---

### `GET /rides/{ride_id}/vehicle`
Passenger-scoped lookup of the vehicle currently assigned to a ride (via `virtual_stop_id → route_waypoints.passenger_ids → route_plans.vehicle_id`). Returns `null` when no route is optimized yet.

**Auth required:** Yes (owner passenger or admin)

**Responses:**
- `200` — `VehicleSnapshot` or `null`
- `403` — Not your ride (and not admin)
- `404` — Ride not found

---

### `GET /rides/`
List all ride requests system-wide (live scope by default).

**Auth required:** Yes (admin or driver only)

**Query params:**
| Param | Type | Default | Notes |
|---|---|---|---|
| status | string | — | Filter: `pending`, `clustered`, `assigned`, `arriving`, `in_progress`, `completed`, `cancelled` |
| mode | string | `live` | `live` \| `presentation_demo` (demo requires `demo_run_id`) |
| demo_run_id | string | — | Required when `mode=presentation_demo` |
| h3_index | string | — | Filter by H3 cell |
| limit | int | 50 | Max 500 |
| offset | int | 0 | Pagination |

**Responses:**
- `200` — List of rides
- `400` — Invalid status value
- `403` — Passenger access blocked
- `422` — Invalid mode / missing `demo_run_id`

---

### `POST /rides/batch`
Create multiple live ride requests in one transaction (same validation as `/rides/request`).

**Auth required:** Yes (any role) — all rows owned by caller, `mode="live"`

**Request body:** `{ "requests": [RideRequestCreate, ...] }`

**Responses:** `201` — List of created rides

---

### `POST /rides/demo-batch?zone=indiranagar|koramangala`
Create 3 isolated presentation riders (`mode="presentation_demo"`) for 1-click HDBSCAN/CVRP demos. Accepts optional custom `pickup_lat|pickup_lng|dest_lat|dest_lng` + labels, or preset zones (Indiranagar default, H3 `8961892eddbffff`).

**Auth required:** Yes (any role)

---

### `POST /rides/demo-shared-batch`
Create up to 3 presentation riders joining one shared-auto route (`{ demo_run_id, riders[] }`).

**Auth required:** Yes (any role)

---

### `DELETE /rides/demo-runs/{demo_run_id}`
Delete one presentation run (rides, virtual stops, route plans, waypoints, tracking events, related notifications) and release any demo vehicle (`DEMO-PRESENTATION-01` → idle). Non-admins can only reset their own runs.

**Auth required:** Yes (owner or admin)

---

### `PATCH /rides/{ride_id}/status`
Update ride status. Validates against allowed statuses. Passengers may only set `cancelled` on their own rides.

**Auth required:** Yes (passenger for own rides → `cancelled` only, driver/admin for any)

**Request body:**
```json
{ "status": "completed" }
```

Valid values: `pending`, `clustered`, `assigned`, `arriving`, `in_progress`, `completed`, `cancelled`

**Responses:**
- `200` — Updated ride + notification fired to passenger
- `400` — Invalid status string
- `403` — Not authorized
- `404` — Ride not found

---

### `DELETE /rides/{ride_id}`
Cancel a ride (sets status to `cancelled`). Cannot cancel `in_progress` or `completed` rides.

**Auth required:** Yes (passenger for own, admin for any)

**Responses:**
- `200` — `{ "message": "Ride request #N has been cancelled successfully" }`
- `400` — Cannot cancel a ride in progress or completed
- `403` — Not authorized
- `404` — Ride not found

---

## Clustering `/cluster`

---

### `POST /cluster/run` (also `POST /cluster/create`)
Trigger HDBSCAN clustering on all pending ride requests.

**Auth required:** Yes (admin or driver)

**Request body:**
```json
{ "resolution": 9, "min_cluster_size": 2 }
```

| Field | Default | Notes |
|---|---|---|
| resolution | 9 | H3 resolution (0-15). 9 ≈ 0.1 km² cells |
| min_cluster_size | 2 | Minimum passengers to form a cluster |

**Responses:**
- `201` — Clustering complete
```json
{
  "cluster_run_id": 5,
  "status": "clustered",
  "total_processed_requests": 24,
  "clusters_formed": 3,
  "noise_requests_count": 2,
  "virtual_stops": [...],
  "clusters": [
    {
      "cluster_id": 1,
      "h3_index": "89618925b73ffff",
      "ride_request_ids": [1, 2, 3],
      "virtual_stop": { "id": 1, "lat": 25.2048, "lng": 55.2708, "passenger_count": 3, ... }
    }
  ]
}
```
- `403` — Passenger access blocked

---

### `GET /cluster/history`
List past cluster runs, newest first.

**Auth required:** Yes (admin or driver)

**Query params:** `?limit=20`

**Responses:**
- `200` — `{ "status": "ok", "runs": [ClusterRunSummary, ...] }`

---

### `GET /cluster/history/{run_id}`
Get full detail of a cluster run including `cluster_summary` JSON.

**Auth required:** Yes (admin or driver)

**Responses:**
- `200` — Full ClusterRunResponse with summary array
- `404` — Run not found

---

## Route Optimization `/route`

---

### `POST /route/optimize`
Solve the Capacitated VRP and assign vehicle routes (live scope). Drivers can only optimise vehicles they own (`vehicles.driver_user_id == self`); admins can use any vehicles.

**Auth required:** Yes (admin or driver)

**Request body:**
```json
{
  "vehicle_ids": [1, 2, 3],
  "virtual_stop_ids": [1, 2, 3, 4],
  "depot_lat": 12.9784,
  "depot_lng": 77.6408,
  "source_cluster_run_id": 5
}
```

| Field | Required | Notes |
|---|---|---|
| vehicle_ids | yes | Must be non-empty; driver calls are filtered to own vehicles (missing → 404) |
| virtual_stop_ids | yes | Can be empty → returns `no_virtual_stops`; must be live-scope stops |
| depot_lat / depot_lng | yes | Starting/ending point for all routes |
| source_cluster_run_id | no | Must be a live-scope cluster run when supplied |

Distance matrix: Stadia (≤25×25) → OSM Dijkstra → haversine; response includes `geometry`/`maneuvers` and `routing_provider: "stadia" | "local-road-matrix"` when Stadia is configured.

**Responses:**
- `200` — Optimization result
```json
{
  "status": "solved",
  "routes": [
    {
      "route_id": "route-1-a3f9c2b1",
      "vehicle_id": 1,
      "total_distance_meters": 4200.5,
      "estimated_duration_seconds": 504.0,
      "waypoints": [
        { "stop_id": null, "lat": 25.2048, "lng": 55.2708, "waypoint_type": "depot", "passenger_ids": [] },
        { "stop_id": 2, "lat": 25.2100, "lng": 55.2800, "waypoint_type": "pickup", "passenger_ids": [3, 4, 5] },
        { "stop_id": null, "lat": 25.2048, "lng": 55.2708, "waypoint_type": "depot", "passenger_ids": [] }
      ]
    }
  ],
  "unassigned_stops": []
}
```
- `400` — Empty vehicle list
- `404` — One or more vehicle/stop IDs not found

---

### `GET /route/history`
List all route plans, newest first.

**Auth required:** Yes (admin or driver)

**Query params:** `?limit=20`

**Responses:**
- `200` — `{ "status": "ok", "routes": [RoutePlanResponse, ...] }`

---

### `GET /route/history/{route_id}`
Get a full route plan including all waypoints.

**Auth required:** Yes (admin or driver)

**Responses:**
- `200` — Full RoutePlanResponse with waypoints array
- `404` — Route not found

---

## Vehicles `/vehicle`

---

### `GET /vehicle/`
List all vehicles.

**Auth required:** Yes (any role)

**Responses:**
- `200` — List of VehicleResponse

---

### `GET /vehicle/idle`
List only idle vehicles (available for assignment).

**Auth required:** Yes (any role)

**Responses:**
- `200` — List of idle VehicleResponse

---

### `POST /vehicle/`
Register a new vehicle. Admin only.

**Auth required:** Yes (admin)

**Request body:**
```json
{ "license_plate": "DXB-001", "capacity": 8, "status": "idle", "lat": 25.2048, "lng": 55.2708 }
```

**Responses:**
- `201` — Vehicle created
- `400` — License plate already exists
- `403` — Not an admin

---

### `PATCH /vehicle/{vehicle_id}`
Update vehicle status, location, or assigned route.

**Auth required:** Yes (admin or driver)

**Request body (all optional):**
```json
{ "status": "en_route", "lat": 25.215, "lng": 55.280, "assigned_route_id": "route-1-abc" }
```

**Responses:**
- `200` — Updated vehicle
- `403` — Passenger access blocked
- `404` — Vehicle not found

---

### `POST /vehicle/assign`
Run Hungarian algorithm to optimally assign idle vehicles to route candidates.
Capacity-aware: pairs where `vehicle.capacity < route.passenger_count` are never matched — over-capacity routes stay in `unassigned_route_ids` (`passenger_count=0` means unknown and stays feasible for all vehicles).

**Auth required:** Yes (admin or driver; drivers are scoped to their own `driver_user_id` idle vehicles)

**Request body:**
```json
{
  "vehicle_ids": [1, 2],
  "route_candidates": [
    { "route_id": "route-1-abc", "lat": 25.21, "lng": 55.27, "passenger_count": 4 },
    { "route_id": "route-2-def", "lat": 25.22, "lng": 55.28, "passenger_count": 3 }
  ]
}
```

**Responses:**
- `200` — Assignment result
```json
{
  "status": "assigned",
  "assignments": [
    { "vehicle_id": 1, "route_id": "route-1-abc", "cost_meters": 1250 }
  ],
  "unassigned_vehicle_ids": [],
  "unassigned_route_ids": []
}
```

---

## Tracking `/tracking`

---

### `GET /tracking/feed`
Snapshot of all vehicles + recent tracking events.

**Auth required:** Yes (admin or driver)

**Query params:** `?limit=10` (events limit, 1-50)

**Responses:**
- `200` — `{ "status": "ok", "vehicles": [VehicleSnapshot, ...], "events": [TrackingEventResponse, ...] }`
- `403` — Passenger access blocked

---

### `GET /tracking/events`
List raw tracking events, newest first.

**Auth required:** Yes (admin or driver)

**Query params:** `?limit=20` (1-100)

**Responses:**
- `200` — List of TrackingEventResponse

---

### `POST /tracking/vehicles/{vehicle_id}/location`
Push a GPS position update for a vehicle. Broadcasts to all WebSocket subscribers instantly.

**Auth required:** Yes (admin or driver)

**Request body:**
```json
{ "lat": 25.215, "lng": 55.278, "status": "en_route", "payload": { "speed_kmh": 45 } }
```

| Field | Required | Notes |
|---|---|---|
| lat | yes | Range ±90 |
| lng | yes | Range ±180 |
| status | no | Overrides vehicle status |
| payload | no | Arbitrary JSON metadata |

**Responses:**
- `200` — Updated VehicleSnapshot
- `403` — Passenger access blocked
- `404` — Vehicle not found

**Side effects:**
- TrackingEvent saved
- Notifications fired to all passengers on the vehicle's route
- Scoped WebSocket broadcast to the vehicle's authorized admin/driver clients and passengers on its route

---

### `WS /tracking/ws`
Live vehicle tracking WebSocket.

**Auth:** the `bearer` WebSocket subprotocol must contain a valid JWT. The
connection is closed with code `4401` if missing or invalid.

**Server broadcasts every 2 seconds. Payloads are scoped server-side:** admins
receive the fleet, drivers receive their assigned vehicle, and passengers
receive only their assigned vehicle.
```json
{
  "type": "tracking_snapshot",
  "vehicles": [
    { "id": 1, "license_plate": "SR-101", "status": "en_route", "lat": 25.215, "lng": 55.278, "assigned_route_id": "route-1-abc" }
  ],
  "events": [...]
}
```

**Also broadcasts on GPS update:**
```json
{
  "type": "vehicle_location_update",
  "vehicle": { ... },
  "event": { ... }
}
```

---

## Notifications `/notifications`

---

### `GET /notifications/`
List the authenticated user's notifications, newest first.

**Auth required:** Yes (any role)

**Query params:**
| Param | Default | Notes |
|---|---|---|
| limit | 20 | Max 100 |
| unread_only | false | Filter to unread only |

**Responses:**
- `200` — `{ "status": "ok", "unread_count": 5, "notifications": [...] }`

---

### `GET /notifications/unread-count`
Quick count of unread notifications.

**Auth required:** Yes (any role)

**Responses:**
- `200` — `{ "status": "ok", "updated_count": 5 }`

---

### `PATCH /notifications/{notification_id}/read`
Mark a single notification as read.

**Auth required:** Yes (own notifications only)

**Responses:**
- `200` — `{ "status": "ok", "notification": { ..., "is_read": true, "read_at": "..." } }`
- `404` — Notification not found or belongs to another user

---

### `PATCH /notifications/read-all`
Mark all unread notifications as read.

**Auth required:** Yes (any role)

**Responses:**
- `200` — `{ "status": "ok", "updated_count": 12 }`

---

### `WS /notifications/ws`
Real-time notification push channel.

**Auth:** the `bearer` WebSocket subprotocol must contain a valid JWT.

**Server broadcasts when any notification is created:**
```json
{
  "type": "notification",
  "vehicles": [],
  "events": []
}
```

---

## Analytics `/analytics`

---

### `GET /analytics/overview`
System-wide aggregated stats. Uses DB-level aggregation — safe at any data volume.

**Auth required:** Yes (admin or driver)

**Responses:**
- `200`
```json
{
  "status": "ok",
  "generated_at": "2026-08-07T10:00:00Z",
  "total_rides": 250,
  "rides_by_status": { "pending": 10, "clustered": 5, "completed": 200, "cancelled": 35 },
  "total_vehicles": 8,
  "idle_vehicles": 3,
  "active_vehicles": 5,
  "total_virtual_stops": 45,
  "total_cluster_runs": 12,
  "total_route_plans": 30,
  "total_tracking_events": 1500,
  "avg_passengers_per_virtual_stop": 3.4,
  "avg_route_distance_meters": 4200.5,
  "avg_trip_distance_meters": 2100.2,
  "route_utilization_percent": 67.5
}
```
- `403` — Passenger access blocked

---

### `GET /analytics/daily`
Per-day ride and route counts for the last N days.

**Auth required:** Yes (admin or driver)

**Query params:** `?days=14` (1-90)

**Responses:**
- `200`
```json
{
  "status": "ok",
  "start_date": "2026-07-25",
  "end_date": "2026-08-07",
  "points": [
    { "day": "2026-07-25", "ride_requests": 18, "clustered_rides": 15, "completed_rides": 12, "cancelled_rides": 2, "route_plans": 4 },
    ...
  ]
}
```
- `400` — days out of range (must be 1-90)

---

## Demand Prediction `/predict`

---

### `GET /predict/demand`
Predict ride demand for a single lat/lng point.

**Auth required:** Yes (any role)

**Query params:**
| Param | Required | Default | Notes |
|---|---|---|---|
| latitude | yes | — | ±90 |
| longitude | yes | — | ±180 |
| resolution | no | 9 | H3 resolution 0-15 |
| lookback_days | no | 30 | Historical window 1-365 |
| reference_time | no | now | ISO datetime for prediction context |

**Responses:**
- `200`
```json
{
  "h3_index": "89618925b73ffff",
  "latitude": 25.2048,
  "longitude": 55.2708,
  "resolution": 9,
  "reference_time": "2026-08-07T08:00:00Z",
  "historical_request_count": 42,
  "predicted_demand": 18.4,
  "model_name": "demand_model.pkl",
  "method": "xgboost_model"
}
```

`method` is `"xgboost_model"` if `ml/models/demand_model.pkl` exists, otherwise `"heuristic_fallback"`.

---

### `GET /predict/heatmap`
Demand heatmap for a geographic bounding box.

**Auth required:** Yes (any role)

**Query params:**
| Param | Required | Notes |
|---|---|---|
| min_lat, min_lng | yes | Bottom-left corner |
| max_lat, max_lng | yes | Top-right corner |
| resolution | no | default 9 |
| lookback_days | no | default 30 |

**Responses:**
- `200` — `{ "status": "ok", "reference_time": "...", "cells": [{ "h3_index", "latitude", "longitude", "historical_request_count", "predicted_demand" }] }`
- `400` — Inverted bounding box (min_lat > max_lat)

---

## Background Jobs `/jobs`

---

### `GET /jobs/status`
Current scheduler state.

**Auth required:** Yes (admin or driver)

**Responses:**
- `200`
```json
{
  "status": "ok",
  "scheduler_running": true,
  "cluster_interval_seconds": 60,
  "demand_interval_seconds": 300,
  "rebalance_interval_seconds": 300,
  "last_cluster_run_at": "2026-08-07T10:00:00Z",
  "last_demand_run_at": "2026-08-07T09:55:00Z",
  "last_rebalance_run_at": "2026-08-07T09:55:00Z",
  "active_tasks": ["cluster_pending_rides", "refresh_demand_snapshots", "rebalance_idle_vehicles", "simulate_ride_dispatch"]
}
```

---

### `GET /jobs/runs`
Recent job execution records.

**Auth required:** Yes (admin or driver)

**Query params:** `?limit=20` (1–100)

**Responses:**
- `200` — List of JobRunResponse

---

### `GET /jobs/demand-snapshots`
Recent demand prediction snapshots.

**Auth required:** Yes (admin or driver)

**Query params:** `?limit=50` (1–200)

**Responses:**
- `200` — List of DemandSnapshotResponse

---

### `GET /jobs/rebalance-suggestions`
Recent vehicle rebalancing suggestions.

**Auth required:** Yes (admin or driver)

**Query params:** `?limit=50` (1–200)

**Responses:**
- `200` — List of VehicleRebalanceSuggestionResponse

---

### `POST /jobs/run/auto-dispatch?mode=live&demo_run_id=...`
Run the full pipeline (cluster → VRP → Hungarian assign) in one call. Default depot `12.9784, 77.6408`; demo mode uses/creates `DEMO-PRESENTATION-01`.

**Auth required:** admin/driver for `mode=live`; any authenticated user for `mode=presentation_demo` (+ `demo_run_id` required)

**Responses:**
- `200` — `{ "job_run_id", "clusters_formed", "routes_optimized", "assigned_rides" }`
- `422` — Invalid mode / missing `demo_run_id`

---

### `POST /jobs/run/clustering?mode=live&demo_run_id=...`
Manually trigger the cluster job immediately (same `mode` access rules as auto-dispatch).

**Auth required:** See above

**Responses:**
- `200` — `{ "job_run_id": 5, "cluster_run_id": 3, "processed_requests": 24, "clusters_formed": 3, "noise_requests_count": 0 }`

---

### `POST /jobs/run/demand`
Manually trigger the demand refresh job.

**Auth required:** Yes (admin or driver)

**Responses:**
- `200` — `{ "job_run_id": 6, "snapshots_created": 12, "lookback_days": 30 }`

---

### `POST /jobs/run/rebalance`
Manually trigger the vehicle rebalancing job.

**Auth required:** Yes (admin or driver)

**Responses:**
- `200` — `{ "job_run_id": 7, "suggestions_created": 4, "idle_vehicles": 4, "candidate_zones": 10 }`

---

## Road Routing `/routing` (Stadia-backed, India-only)

All points must satisfy `is_india_location` (6.5–35.7 / 68.1–97.4); Stadia key stays server-side.

### `GET /routing/route?from_lat&from_lng&to_lat&to_lng&traffic=false`
Drivable route with `geometry`, `distanceMeters`, `durationSeconds`, `maneuvers`. `traffic=true` uses `auto_traffic` costing.

**Auth:** any role. `422` outside India, `502` no drivable route / Stadia failure.

### `GET /routing/nearest-road?lat&lng`
Snap a point to the nearest road (`{ lat, lng, ... }`).

**Auth:** any role. `404` no nearby road.

### `POST /routing/map-match` (body: 2–100 `{ lat, lng|lon }`)
Map-match a GPS trace → route details.

**Auth:** any role. `422` unless 2–100 India points.

### `POST /routing/matrix` (body: `{ sources[], targets[], costing? }`)
Stadia cost matrix; each side must contain 1–25 India points.

**Auth:** admin/driver only (`403` otherwise).

---

## Geocoding `/geocode` (Stadia-backed, India-filtered)

### `GET /geocode/suggest?query&lat&lng`
Autocomplete (query ≥3 chars; `lat`+`lng` must come together for focus point). Returns `[{ lat, lng, label, raw }]`, India-only.

### `GET /geocode/search?query`
Forward geocode (query ≥2 chars). Returns India-only list; frontend `search()` throws `Location not found` when empty.

### `GET /geocode/reverse?lat&lng`
Reverse geocode → `{ lat, lng, label }`. `422` outside India, `404` when no feature.

**Auth (all three):** any role. Stadia failures surface as `502`.

---

## Map Tiles `/maps/stadia` (authenticated Stadia proxy)

Prevents `api_key` leakage: style JSON is rewritten so every Stadia URL points at `/maps/stadia/resource/*`.

### `GET /maps/stadia/style.json`
Proxied MapLibre style (`Cache-Control: private, max-age=300`).

### `GET /maps/stadia/resource/{resource_path:path}`
Proxied tiles/sprites/glyphs (`Cache-Control: public, max-age=86400`; JSON bodies rewritten).

**Auth (both):** any role (required — this is why the map needs login). Stadia failures surface as `502`.

---

## HTTP Status Codes Used

| Code | Meaning |
|---|---|
| 200 | OK |
| 201 | Created |
| 400 | Bad request — invalid input, duplicate, or constraint violation |
| 401 | Unauthorized — missing, expired, or invalid token |
| 403 | Forbidden — authenticated but insufficient role |
| 404 | Not found |
| 422 | Unprocessable entity — Pydantic validation failure |
| 500 | Internal server error |
