# Database Schema

12 tables. Supabase PostgreSQL + PostGIS in production, SQLite only when explicitly configured for local development.

---

## Entity Relationship Overview

```
users ──────────────────────────────────────────────────────────────────┐
  │                                                                      │
  ├── ride_requests (user_id FK)                                         │
  │       │                                                              │
  │       └── virtual_stops (virtual_stop_id FK)                        │
  │               │                                                      │
  │               └── cluster_runs (cluster_summary JSON refs stop ids) │
  │                       │                                              │
  │                       └── route_plans (source_cluster_run_id FK)    │
  │                               │                                      │
  │                               ├── route_waypoints (route_plan_id FK)│
  │                               │                                      │
  │                               └── vehicles (vehicle_id FK)          │
  │                                       │                              │
  │                                       ├── tracking_events            │
  │                                       │                              │
  │                                       └── vehicle_rebalance_suggestions
  │                                               │
  │                                               └── job_runs ─────────┘
  │                                                       │
  │                                                       └── demand_snapshots
  │
  └── notifications (user_id FK)
```

---

## Table: `users`

Stores all user accounts — passengers, drivers, and admins.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PK, index | Auto-increment |
| `name` | VARCHAR | NOT NULL | Display name |
| `email` | VARCHAR | NOT NULL, UNIQUE, index | Login identifier |
| `phone` | VARCHAR | default `""` | Optional contact |
| `password_hash` | VARCHAR | NOT NULL | Legacy seed placeholder; user passwords are managed by Clerk |
| `role` | VARCHAR | NOT NULL, default `"passenger"` | `passenger` / `driver` / `admin` |
| `created_at` | TIMESTAMPTZ | server default NOW() | |

**Relationships:**
- `ride_requests` → one-to-many (user has many rides)
- `notifications` → one-to-many, cascade delete

---

## Table: `ride_requests`

Every passenger ride request — from creation through completion.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PK, index | |
| `user_id` | INTEGER | FK → users.id, NOT NULL | Requesting passenger |
| `pickup_lat` | FLOAT | NOT NULL | Pickup latitude |
| `pickup_lng` | FLOAT | NOT NULL | Pickup longitude |
| `dest_lat` | FLOAT | NOT NULL | Destination latitude |
| `dest_lng` | FLOAT | NOT NULL | Destination longitude |
| `status` | VARCHAR | NOT NULL, default `"pending"` | See status flow below |
| `h3_index` | VARCHAR | index, nullable | H3 cell at resolution 9 |
| `cluster_id` | INTEGER | nullable | Set after clustering |
| `virtual_stop_id` | INTEGER | FK → virtual_stops.id, nullable | Set after clustering |
| `pickup_location` | PortableGeometry | nullable | PostGIS POINT (Postgres) or String (SQLite) |
| `destination_location` | PortableGeometry | nullable | PostGIS POINT (Postgres) or String (SQLite) |
| `request_time` | TIMESTAMPTZ | server default NOW() | |
| `pickup_label` | VARCHAR | nullable | Human-readable label from client |
| `destination_label` | VARCHAR | nullable | Human-readable label from client |
| `ride_option_id` | VARCHAR | nullable | e.g. `"shared"`, `"premium"` |
| `ride_option_name` | VARCHAR | nullable | Display name |
| `ride_option_price` | VARCHAR | nullable | Stored as string for display |

**Status flow:**
```
pending → clustered → assigned → arriving → in_progress → completed
                                                        ↘ cancelled
```

**Relationships:**
- `user` → many-to-one (belongs to user)
- `virtual_stop` → many-to-one (belongs to virtual stop after clustering)

---

## Table: `virtual_stops`

Computed pickup points — one per passenger cluster, snapped to a real road node.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PK, index | |
| `cluster_id` | INTEGER | NOT NULL | Links to cluster group (not FK, logical) |
| `h3_index` | VARCHAR | index, nullable | H3 cell this stop belongs to |
| `lat` | FLOAT | NOT NULL | Snapped latitude |
| `lng` | FLOAT | NOT NULL | Snapped longitude |
| `snapped_node_id` | VARCHAR | nullable | OSM node ID from OSMnx, `"none"` if fallback |
| `passenger_count` | INTEGER | default 0 | Number of passengers at this stop |
| `coordinates` | PortableGeometry | nullable | PostGIS POINT |
| `created_at` | TIMESTAMPTZ | server default NOW() | |

**Relationships:**
- `ride_requests` → one-to-many (stop serves many rides)

---

## Table: `cluster_runs`

Audit log of every HDBSCAN clustering execution.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PK, index | |
| `run_uuid` | VARCHAR | NOT NULL, UNIQUE, index | UUID for idempotency |
| `resolution` | INTEGER | NOT NULL | H3 resolution used (default 9) |
| `min_cluster_size` | INTEGER | NOT NULL | HDBSCAN min_cluster_size param |
| `status` | VARCHAR | NOT NULL, default `"clustered"` | `clustered` / `no_pending_requests` |
| `total_processed_requests` | INTEGER | NOT NULL, default 0 | |
| `clusters_formed` | INTEGER | NOT NULL, default 0 | |
| `noise_requests_count` | INTEGER | NOT NULL, default 0 | Outlier rides not grouped |
| `created_by_user_id` | INTEGER | FK → users.id, nullable | Who triggered it |
| `cluster_summary` | JSON | nullable | Array of cluster details — see below |
| `created_at` | TIMESTAMPTZ | server default NOW() | |

**`cluster_summary` JSON structure:**
```json
[
  {
    "cluster_id": 1,
    "h3_index": "89618925b73ffff",
    "ride_request_ids": [1, 2, 3],
    "virtual_stop_id": 1,
    "virtual_stop_lat": 12.9716,
    "virtual_stop_lng": 77.5946,
    "passenger_count": 3,
    "snapped_node_id": "123456789"
  }
]
```

---

## Table: `route_plans`

One record per optimized vehicle route produced by OR-Tools VRP.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PK, index | |
| `route_id` | VARCHAR | NOT NULL, UNIQUE, index | e.g. `"route-1-a3f9c2b1"` |
| `vehicle_id` | INTEGER | FK → vehicles.id, NOT NULL | Assigned vehicle |
| `source_cluster_run_id` | INTEGER | FK → cluster_runs.id, nullable | Which cluster run this came from |
| `status` | VARCHAR | NOT NULL, default `"solved"` | `solved` / `failed` |
| `depot_lat` | FLOAT | NOT NULL | Starting/ending depot |
| `depot_lng` | FLOAT | NOT NULL | |
| `total_distance_meters` | FLOAT | NOT NULL, default 0.0 | Sum of all legs |
| `estimated_duration_seconds` | FLOAT | NOT NULL, default 0.0 | distance / 8.33 m/s (~30 km/h) |
| `created_by_user_id` | INTEGER | FK → users.id, nullable | Who triggered optimization |
| `metadata` | JSON | nullable | `{ vehicle_capacity, assigned_stop_ids[], source_cluster_run_id }` |
| `created_at` | TIMESTAMPTZ | server default NOW() | |

**Relationships:**
- `vehicle` → many-to-one
- `source_cluster_run` → many-to-one
- `waypoints` → one-to-many (ordered by sequence), cascade delete

---

## Table: `route_waypoints`

Ordered stop sequence for each route plan.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PK, index | |
| `route_plan_id` | INTEGER | FK → route_plans.id, NOT NULL | |
| `sequence` | INTEGER | NOT NULL | 0 = depot start, N = depot end |
| `stop_id` | INTEGER | nullable | FK to virtual_stops (nullable = depot) |
| `lat` | FLOAT | NOT NULL | |
| `lng` | FLOAT | NOT NULL | |
| `waypoint_type` | VARCHAR | NOT NULL | `depot` / `pickup` / `dropoff` |
| `passenger_ids` | JSON | nullable | List of ride_request IDs at this stop |
| `created_at` | TIMESTAMPTZ | server default NOW() | |

---

## Table: `vehicles`

The fleet — one record per physical vehicle.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PK, index | |
| `license_plate` | VARCHAR | NOT NULL, UNIQUE, index | |
| `capacity` | INTEGER | NOT NULL | Max passenger seats |
| `status` | VARCHAR | NOT NULL, default `"idle"` | `idle` / `active` / `en_route` / `offline` |
| `lat` | FLOAT | nullable | Current GPS latitude |
| `lng` | FLOAT | nullable | Current GPS longitude |
| `assigned_route_id` | VARCHAR | nullable | route_plans.route_id (string FK) |
| `current_location` | PortableGeometry | nullable | PostGIS POINT |
| `created_at` | TIMESTAMPTZ | server default NOW() | |

---

## Table: `tracking_events`

Raw GPS event log — one row per location update or status change.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PK, index | |
| `vehicle_id` | INTEGER | FK → vehicles.id, nullable, index | |
| `ride_request_id` | INTEGER | FK → ride_requests.id, nullable, index | |
| `route_plan_id` | INTEGER | FK → route_plans.id, nullable, index | |
| `event_type` | VARCHAR | NOT NULL | e.g. `"vehicle_location_update"` |
| `status` | VARCHAR | nullable | Vehicle status at time of event |
| `lat` | FLOAT | nullable | GPS latitude |
| `lng` | FLOAT | nullable | GPS longitude |
| `payload` | JSON | nullable | Arbitrary extra data from client |
| `created_at` | TIMESTAMPTZ | server default NOW(), index | |

---

## Table: `notifications`

Per-user notification inbox. Every action in the system fires one or more notifications.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PK, index | |
| `user_id` | INTEGER | FK → users.id, NOT NULL, index | Recipient |
| `notification_type` | VARCHAR | NOT NULL, index | e.g. `"ride_requested"`, `"route_assigned"` |
| `title` | VARCHAR | NOT NULL | Short display title |
| `message` | VARCHAR | NOT NULL | Full notification text |
| `related_entity_type` | VARCHAR | nullable | e.g. `"ride_request"`, `"vehicle"` |
| `related_entity_id` | INTEGER | nullable, index | ID of the related record |
| `metadata` | JSON | nullable | Extra context (stored as `notification_metadata` in ORM) |
| `is_read` | BOOLEAN | NOT NULL, default False | |
| `read_at` | TIMESTAMPTZ | nullable | Set when marked read |
| `created_at` | TIMESTAMPTZ | server default NOW(), index | |

**Notification types used in the system:**
```
ride_requested           → passenger submits ride
ride_status_updated      → ride status changes
ride_cancelled           → ride cancelled
route_assigned           → route optimized for passenger's stop
route_optimized          → confirmation to the dispatcher
vehicle_tracking_update  → passenger notified of vehicle position
vehicle_location_logged  → driver confirmation of GPS update
seed_complete            → seed script finished
```

---

## Table: `job_runs`

Audit log for every background job execution (scheduled or manual).

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PK, index | |
| `job_name` | VARCHAR | NOT NULL, index | `cluster_pending_rides` / `refresh_demand_snapshots` / `rebalance_idle_vehicles` / `simulate_ride_dispatch` |
| `status` | VARCHAR | NOT NULL, default `"running"` | `running` / `success` / `failed` |
| `triggered_by_user_id` | INTEGER | FK → users.id, nullable | NULL = scheduled |
| `is_scheduled` | BOOLEAN | NOT NULL, default True | False = manual trigger |
| `summary` | JSON | nullable | Result stats — counts, IDs, etc. |
| `error_message` | VARCHAR | nullable | Populated on failure |
| `started_at` | TIMESTAMPTZ | NOT NULL, server default NOW() | |
| `finished_at` | TIMESTAMPTZ | nullable | NULL until complete |

---

## Table: `demand_snapshots`

Predicted demand per H3 zone — output of the demand refresh job.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PK, index | |
| `job_run_id` | INTEGER | FK → job_runs.id, NOT NULL, index | Which job created this |
| `h3_index` | VARCHAR | NOT NULL, index | H3 cell identifier |
| `lat` | FLOAT | NOT NULL | Cell center latitude |
| `lng` | FLOAT | NOT NULL | Cell center longitude |
| `lookback_days` | INTEGER | NOT NULL, default 30 | Historical window used |
| `historical_request_count` | INTEGER | NOT NULL, default 0 | Actual rides in window |
| `predicted_demand` | FLOAT | NOT NULL, default 0.0 | Model output |
| `model_name` | VARCHAR | nullable | `"demand_model.pkl"` or `"no_model_available"` |
| `method` | VARCHAR | nullable | `"xgboost_model"` or `"heuristic_fallback"` |
| `created_at` | TIMESTAMPTZ | server default NOW() | |

---

## Table: `vehicle_rebalance_suggestions`

Advisory suggestions for repositioning idle vehicles to high-demand zones.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | INTEGER | PK, index | |
| `job_run_id` | INTEGER | FK → job_runs.id, NOT NULL, index | Which job created this |
| `vehicle_id` | INTEGER | FK → vehicles.id, NOT NULL, index | Which idle vehicle |
| `target_h3_index` | VARCHAR | NOT NULL, index | Destination zone |
| `target_lat` | FLOAT | NOT NULL | Zone center latitude |
| `target_lng` | FLOAT | NOT NULL | Zone center longitude |
| `score` | FLOAT | NOT NULL, default 0.0 | Predicted demand score |
| `reason` | VARCHAR | nullable | Human-readable explanation |
| `created_at` | TIMESTAMPTZ | server default NOW() | |

---

## PortableGeometry Type

The `PortableGeometry` custom SQLAlchemy type handles the PostgreSQL/SQLite difference:

- **PostgreSQL** → uses `geoalchemy2.Geometry("POINT", srid=4326)` — full PostGIS
- **SQLite** → degrades to `String` — geometry stored as text, spatial queries not available

All geospatial computation (distance, clustering, snapping) is done in Python, not in the DB, so SQLite works correctly for all features except raw PostGIS spatial queries.

---

## Indexes Summary

| Table | Indexed Columns |
|---|---|
| `users` | id, email |
| `ride_requests` | id, h3_index |
| `virtual_stops` | id, h3_index |
| `cluster_runs` | id, run_uuid |
| `route_plans` | id, route_id |
| `vehicles` | id, license_plate |
| `tracking_events` | id, vehicle_id, ride_request_id, route_plan_id, created_at |
| `notifications` | id, user_id, notification_type, related_entity_id, created_at |
| `job_runs` | id, job_name |
| `demand_snapshots` | id, job_run_id, h3_index |
| `vehicle_rebalance_suggestions` | id, job_run_id, vehicle_id, target_h3_index |
