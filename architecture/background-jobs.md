# Background Jobs

Four async workers start automatically when the server starts and run continuously.

---

## How It Works

Jobs are managed by `backend/services/background_jobs.py`. On startup (`lifespan` in `main.py`), four asyncio Tasks are created:

```python
loop.create_task(_run_periodic("cluster_pending_rides",    60,  run_cluster_job))
loop.create_task(_run_periodic("refresh_demand_snapshots", 300, run_demand_refresh_job))
loop.create_task(_run_periodic("rebalance_idle_vehicles",  300, run_vehicle_rebalance_job))
loop.create_task(_run_periodic("simulate_ride_dispatch",   5,   run_simulate_ride_dispatch_job))
```

Each task:
1. Opens a fresh DB session
2. Runs the job function
3. Closes the DB session
4. Sleeps for the interval
5. Repeats

On server shutdown, all tasks are cancelled and awaited via `stop_background_jobs()`.

---

## Job 1: `cluster_pending_rides`

**Interval:** every 60 seconds  
**Function:** `run_cluster_job(db)`  
**Manual trigger:** `POST /jobs/run/clustering`

### What it does

Takes all `pending` ride requests and groups them into clusters with virtual pickup stops.

### Step-by-step

```
1. Query all RideRequests where status = "pending"
   → if none: record ClusterRun(status="no_pending_requests"), return early

2. Compute H3 index for any rides missing one
   get_h3_index(pickup_lat, pickup_lng, resolution=9)

3. Partition rides into H3 buckets
   { "89618925b73ffff": [ride1, ride2, ride3], ... }

4. For each H3 bucket:
   a. Run HDBSCAN → get cluster labels
   b. For each cluster group (label != -1):
      - K-Medoids → candidate stop lat/lng
      - OSMnx → build road graph (2.5km radius)
      - snap_to_road → nearest road node
      - Create VirtualStop (cluster_id, h3_index, lat, lng, snapped_node_id, passenger_count)
      - Update each RideRequest in cluster:
          cluster_id = next_cluster_id
          virtual_stop_id = virtual_stop.id
          status = "clustered"

5. Create ClusterRun record:
   { run_uuid, resolution, min_cluster_size, status,
     total_processed_requests, clusters_formed,
     noise_requests_count, cluster_summary (JSON) }

6. Commit all changes
```

### Writes to
- `virtual_stops` — new rows per cluster
- `ride_requests` — updates status, cluster_id, virtual_stop_id
- `cluster_runs` — audit record
- `job_runs` — execution record

### Error handling
On exception: rollback, merge job_run, mark as `failed` with error_message, commit, re-raise.

---

## Job 2: `refresh_demand_snapshots`

**Interval:** every 300 seconds (5 minutes)  
**Function:** `run_demand_refresh_job(db)`  
**Manual trigger:** `POST /jobs/run/demand`

### What it does

For each H3 zone that has had rides in the last 30 days, predicts current demand and saves a snapshot.

### Step-by-step

```
1. Query RideRequests from last lookback_days (default 30)

2. Collect unique H3 indexes from those rides
   (compute if missing: get_h3_index(pickup_lat, pickup_lng))

3. For each H3 index:
   a. Count historical rides in this zone in lookback window
   b. Build feature vector:
      { hour, day_of_week, h3_zone, historical_count, is_weekend }
   c. Predict via XGBoost model (or heuristic fallback)
   d. Get cell center: get_h3_center(h3_index) → (lat, lng)
   e. Create DemandSnapshot:
      { job_run_id, h3_index, lat, lng,
        historical_request_count, predicted_demand,
        model_name, method }

4. Commit all snapshots
```

### Writes to
- `demand_snapshots` — one row per active H3 zone
- `job_runs` — execution record

---

## Job 3: `rebalance_idle_vehicles`

**Interval:** every 300 seconds (5 minutes)  
**Function:** `run_vehicle_rebalance_job(db)`  
**Manual trigger:** `POST /jobs/run/rebalance`

### What it does

Looks at idle vehicles and high-demand zones, then creates advisory suggestions for which vehicle should move where.

### Step-by-step

```
1. Query idle vehicles (status = "idle")
   → if none: record job success with suggestions_created=0, return early

2. Query rides from last 30 days, count per H3 zone
   demand_cells = { h3_index: ride_count, ... }

3. For each zone, predict demand (XGBoost / heuristic)
4. Sort zones by predicted_demand descending, take top 10

5. For each idle vehicle:
   a. Find the nearest high-demand zone (haversine from vehicle lat/lng)
   b. Create VehicleRebalanceSuggestion:
      { job_run_id, vehicle_id, target_h3_index,
        target_lat, target_lng, score, reason }

6. Commit all suggestions
```

### Important: suggestions are advisory only
Vehicles are NOT automatically repositioned. The suggestions appear in `GET /jobs/rebalance-suggestions` for an admin/dispatcher to act on.

### Writes to
- `vehicle_rebalance_suggestions` — one row per idle vehicle
- `job_runs` — execution record

---

## Job 4: `simulate_ride_dispatch`

**Interval:** every 5 seconds  
**Function:** `run_simulate_ride_dispatch_job(db)`

### What it does

Advances the status of active rides through the lifecycle for demo purposes. This simulates a real dispatch system without requiring actual driver apps.

### Transition table

```
pending      → assigned
clustered    → assigned
assigned     → arriving
arriving     → in_progress
in_progress  → completed
```

### Step-by-step

```
1. Query all RideRequests where status IN
   (pending, clustered, assigned, arriving, in_progress)

2. For each ride:
   a. Apply transition
   b. Create notification for passenger:
      "Your ride request #N changed from X to Y"

3. Commit all changes
```

### Writes to
- `ride_requests` — updates status for all active rides
- `notifications` — one per ride per cycle
- `job_runs` — execution record

> This job runs every 5 seconds so in a live demo, a freshly submitted ride will go from `pending` → `completed` in about 25 seconds.

---

## Live Tracking Broadcast (not a job, but runs in background)

**Interval:** every 2 seconds  
**Function:** `broadcast_live_feed()` in `backend/routers/tracking.py`  
**Started by:** `tracking.start_simulation()` in `main.py` lifespan

### What it does

Continuously queries the DB for all vehicles and recent events, then broadcasts a snapshot to every connected WebSocket client.

```python
while True:
    vehicles = db.query(Vehicle).all()
    events = db.query(TrackingEvent).order_by(...).limit(10).all()
    payload = { "type": "tracking_snapshot", "vehicles": [...], "events": [...] }
    await manager.broadcast(json.dumps(payload))
    await asyncio.sleep(2)
```

This is separate from the per-update broadcast triggered by `POST /tracking/vehicles/{id}/location`.

### Writes to
Nothing — read-only query, broadcast only.

---

## Monitoring Jobs

### Via API
```
GET /jobs/status         → scheduler running state + last run times
GET /jobs/runs           → execution history (last N job_runs)
GET /jobs/demand-snapshots     → demand prediction results
GET /jobs/rebalance-suggestions → rebalancing advice
```

### Scheduler state object
```python
STATE = SchedulerState(
    running=True,
    last_cluster_run_at=datetime,
    last_demand_run_at=datetime,
    last_rebalance_run_at=datetime,
    last_dispatch_run_at=datetime,
    active_tasks=["cluster_pending_rides", ...]
)
```

### Manual trigger
All jobs (except the dispatch simulation) can be triggered on-demand:
```
POST /jobs/run/clustering   → runs run_cluster_job immediately
POST /jobs/run/demand       → runs run_demand_refresh_job immediately
POST /jobs/run/rebalance    → runs run_vehicle_rebalance_job immediately
```
Manual triggers set `is_scheduled=False` in the `job_runs` record for auditability.
