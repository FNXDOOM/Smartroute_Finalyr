# Algorithms

How each AI and optimization algorithm works, why it was chosen, and exactly where it lives in the codebase.

---

## 1. H3 Spatial Partitioning

**File:** `backend/services/clustering/h3_partitioner.py`  
**Library:** `h3` (Uber)

### What it does
Divides the map into a uniform hexagonal grid. Each ride request is assigned to the H3 cell that contains its pickup coordinates. Rides in the same cell are processed together before clustering.

### Why hexagons
Hexagons have equal distance from center to all 6 neighbors (unlike squares where diagonal neighbors are further). This gives more consistent clustering behavior across directions.

### Resolution 9
At resolution 9, each cell covers approximately 0.1 km² (roughly 200m across). This is small enough to group genuinely nearby passengers but large enough to have multiple rides per cell.

### In the code
```python
h3_index = get_h3_index(lat, lng, resolution=9)
# returns a string like "89618925b73ffff"

buckets = partition_requests(ride_requests, resolution=9)
# returns { h3_index: [ride1, ride2, ...], ... }
```

---

## 2. HDBSCAN Passenger Clustering

**File:** `backend/services/clustering/hdbscan_clusterer.py`  
**Library:** `hdbscan` (falls back to `sklearn.DBSCAN`)

### What it does
Groups passengers within each H3 bucket by geographic proximity. Passengers who are close enough to share a single pickup stop are placed in the same cluster. Passengers too isolated to cluster are labeled as noise (`-1`).

### Why HDBSCAN over K-means
- K-means requires knowing the number of clusters upfront — we don't know how many groups will form
- HDBSCAN is density-based — it finds clusters of any shape and naturally handles outliers
- HDBSCAN is hierarchical — more stable than flat DBSCAN on varying densities

### Key parameters
```python
hdbscan.HDBSCAN(
    min_cluster_size=2,           # minimum passengers to form a cluster
    metric="haversine",           # great-circle distance, not Euclidean
    cluster_selection_epsilon=50/6_371_000  # ~50m in radians
)
```

The `cluster_selection_epsilon` (50m) means clusters within 50m of each other may be merged. This prevents one street corner generating 5 separate stops.

### Coordinate handling
Coordinates are passed as radians to the haversine metric:
```python
labels = clusterer.fit_predict(np.radians(coords))
# coords shape: (n_rides, 2) — [[lat, lng], ...]
```

### Output
```python
labels = cluster_passengers(requests, min_cluster_size=2)
# array like [0, 0, 1, 1, 1, -1, 2, 2]
# -1 = noise (no pickup stop generated for these)

groups = get_cluster_groups(requests, labels)
# { 0: [ride_a, ride_b], 1: [ride_c, ride_d, ride_e], 2: [ride_f, ride_g] }
```

---

## 3. K-Medoids Virtual Stop Placement

**File:** `backend/services/stops/virtual_stop_generator.py`  
**Library:** `sklearn_extra.cluster.KMedoids`

### What it does
Given a cluster of passengers, selects the best representative pickup point. Unlike K-means which returns a computed centroid (which may be mid-air or in a building), K-Medoids always picks an actual data point — in this case, one of the actual passenger pickup locations.

### Why K-Medoids over centroid
A centroid of `[(25.201, 55.270), (25.203, 55.272)]` might land in a pedestrian walkway. K-Medoids picks the actual coordinate that minimizes sum of distances to all other points — guaranteed to be a real street location.

### In the code
```python
kmedoids = KMedoids(n_clusters=1, metric="euclidean", random_state=42)
kmedoids.fit(coords)
stop_lat, stop_lng = coords[kmedoids.medoid_indices_[0]]
```

`n_stops=1` per cluster — one virtual stop serves all passengers in a cluster.

### Fallback
If `sklearn_extra` is unavailable, falls back to geometric centroid (`coords.mean(axis=0)`).

---

## 4. OSMnx Road Snapping

**File:** `backend/services/stops/road_snapper.py`  
**Library:** `osmnx`, `networkx`

### What it does
Takes the K-Medoids stop coordinate and moves it to the nearest drivable road node in the OpenStreetMap road network. This ensures vehicles can actually reach the stop.

### Process
```
K-Medoids stop point (may be in a park or building)
        ↓
osmnx.graph_from_point(center, dist=2500, network_type="drive")
→ downloads all drivable roads within 2.5km
        ↓
osmnx.distance.nearest_nodes(graph, X=lng, Y=lat)
→ finds the OSM node ID closest to the stop point
        ↓
snapped_lat, snapped_lng = graph.nodes[nearest_node]["y"], ["x"]
snapped_node_id = str(nearest_node)
```

### OSM data caching
OSMnx caches downloaded road graphs in `~/.cache/osmnx/`. The first clustering run in a new area downloads the graph; subsequent runs for the same area are instant.

### Fallback
If OSMnx is not installed or the download fails, `snap_to_road` returns the original coordinates with `snapped_node_id = "none"`. Clustering still works — stops just won't be road-aligned.

---

## 5. OR-Tools CVRP Solver

**File:** `backend/services/routing/vrp_solver.py`  
**Library:** `ortools` (Google)

### What it does
Solves the Capacitated Vehicle Routing Problem (CVRP): given a set of virtual stops with passenger demands, and a fleet of vehicles with capacity constraints, find the optimal assignment of stops to vehicles and the optimal visit order — minimizing total travel distance.

### Problem formulation
```
Depot: starting and ending point for all routes
Stops: virtual stops with passenger_count as demand
Vehicles: each with capacity constraint

Minimize: total distance traveled by all vehicles
Subject to: each stop visited exactly once
            vehicle load never exceeds capacity
            all routes start and end at depot
```

### Distance matrix
A symmetric N×N matrix of haversine distances between all stops (including depot at index 0):
```python
matrix[i][j] = haversine_meters(stops[i]["lat"], stops[i]["lng"],
                                stops[j]["lat"], stops[j]["lng"])
```

### Search strategy
```python
params.first_solution_strategy = PATH_CHEAPEST_ARC   # greedy initial solution
params.local_search_metaheuristic = GUIDED_LOCAL_SEARCH  # improve iteratively
params.time_limit.seconds = 10  # hard timeout
```

### Output
```python
{
  "status": "solved",
  "routes": [
    { "vehicle_idx": 0, "stop_indices": [0, 2, 4, 0], "distance_m": 4200 }
  ],
  "total_distance_m": 8500
}
```

---

## 6. Hungarian Algorithm — Vehicle Assignment

**File:** `backend/services/assignment/hungarian_assigner.py`  
**Library:** `scipy.optimize.linear_sum_assignment`

### What it does
Optimally assigns idle vehicles to route starting points. Given a cost matrix where `cost[i][j]` = distance from vehicle i to route j's depot, finds the one-to-one assignment that minimizes total cost.

### Why Hungarian over greedy
Greedy (assign each vehicle to its nearest route) can produce globally suboptimal results. The Hungarian algorithm guarantees a globally optimal assignment in O(n³) time.

### Example
```
          Route A   Route B   Route C
Vehicle 1   500m     2000m     1500m
Vehicle 2   2500m    400m      1800m
Vehicle 3   1200m    1100m     300m

Greedy: V1→A(500), V2→B(400), V3→C(300) = 1200m total  ✓ (happens to be optimal here)

Hungarian always guarantees the global minimum.
```

### In the code
```python
cost_array = np.array(cost_matrix)
row_ind, col_ind = linear_sum_assignment(cost_array)
# returns ([0, 1, 2], [0, 1, 2]) → vehicle 0→route 0, vehicle 1→route 1, etc.
```

---

## 7. XGBoost Demand Forecasting

**File:** `backend/services/prediction/demand_model.py`  
**Model:** `ml/models/demand_model.pkl`

### What it does
Predicts how many ride requests will originate from a given H3 zone at a given time. Used by the demand heatmap, the rebalancing job, and the demand snapshot job.

### Features (5 inputs)

| Feature | How computed | Why it matters |
|---|---|---|
| `hour` | `reference_time.hour` | Morning/evening rush |
| `day_of_week` | `reference_time.weekday()` (0=Mon) | Weekend vs weekday patterns |
| `h3_zone` | `abs(hash(h3_index)) % 10_000` | Zone identity (encoded) |
| `historical_count` | DB count of rides in zone in last N days | Base demand level |
| `is_weekend` | 1 if day_of_week ≥ 5 | Weekend multiplier |

### Model training
Trained with `scripts/train_demand_model_synthetic.py` on 172,800 synthetic samples covering 180 days × 40 zones × 24 hours. MAE ≈ 3.1 rides per zone-hour.

### Heuristic fallback
If `ml/models/demand_model.pkl` does not exist, `_fallback_prediction` applies time-of-day multipliers:
- Rush hours (7-10am, 5-8pm): `demand × 1.35`
- Late night (10pm-5am): `demand × 0.8`
- Weekend: `demand × 0.9`
- Monday: `demand × 1.05`

### LRU cache
The model is loaded once and cached:
```python
@lru_cache(maxsize=1)
def load_model() -> Any | None:
    ...
```
No file I/O on subsequent prediction calls.

---

## 8. A* Shortest Path

**File:** `backend/services/routing/astar_router.py`  
**Library:** `networkx`

### What it does
Computes the shortest path between two OSM road nodes using the A* algorithm on the downloaded road graph.

### Current status
This module is implemented but not called anywhere in the current pipeline. The VRP solver uses a haversine straight-line distance matrix (sufficient for optimization). A* would be used if turn-by-turn navigation is added in the future.

```python
path = nx.astar_path(graph, origin_node, dest_node, weight="length")
# returns ordered list of OSM node IDs
```

---

## Algorithm Selection Summary

| Problem | Why this algorithm |
|---|---|
| Spatial partitioning | H3 gives uniform cell sizes — avoids boundary edge cases that grid squares have |
| Passenger clustering | HDBSCAN handles variable density and unknown cluster count — K-means can't |
| Stop placement | K-Medoids picks a real coordinate — centroids can land off-road |
| Road snapping | OSMnx gives authoritative road data from OpenStreetMap — no API costs |
| Route optimization | OR-Tools is Google's production VRP solver — handles constraints and scales well |
| Vehicle assignment | Hungarian algorithm is provably optimal for one-to-one assignment |
| Demand forecasting | XGBoost is fast, handles tabular data well, interpretable feature importances |
