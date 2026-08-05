"""
Full backend test suite — tests every endpoint systematically.
Run with: python scripts/test_backend_full.py
"""
import json
import sys
import time
import requests

BASE = "http://127.0.0.1:8000"
PASS = "✓"
FAIL = "✗"
WARN = "⚠"

# Use a unique run suffix so re-runs don't collide with existing DB rows
RUN_ID = str(int(time.time()))[-6:]

results = {"passed": 0, "failed": 0, "warnings": 0}

# ── helpers ──────────────────────────────────────────────────────────────────

def check(label, response, expected_status, key_check=None):
    ok = response.status_code == expected_status
    if ok and key_check:
        try:
            data = response.json()
            ok = key_check(data)
        except Exception:
            ok = False
    symbol = PASS if ok else FAIL
    if ok:
        results["passed"] += 1
    else:
        results["failed"] += 1
    print(f"  {symbol} {label}  [{response.status_code}]")
    if not ok:
        try:
            print(f"      → {json.dumps(response.json())[:200]}")
        except Exception:
            print(f"      → {response.text[:200]}")
    return response.json() if ok else None


def section(title):
    print(f"\n{'─'*55}")
    print(f"  {title}")
    print(f"{'─'*55}")


# ── root ─────────────────────────────────────────────────────────────────────

section("Root")
r = requests.get(f"{BASE}/")
check("GET /  (health)", r, 200, lambda d: "SmartRouteAI" in d.get("message", ""))

# ── auth ─────────────────────────────────────────────────────────────────────

section("Auth — Register")

# Should block admin self-assign
r = requests.post(f"{BASE}/auth/register", json={
    "name": "Hacker", "email": "hacker@x.com", "password": "pw", "role": "admin"
})
check("POST /auth/register  (admin role blocked)", r, 400)

# Register passenger
r = requests.post(f"{BASE}/auth/register", json={
    "name": "Test Passenger", "email": f"testpass_{RUN_ID}@x.com", "password": "pass1234", "role": "passenger"
})
check("POST /auth/register  (passenger)", r, 201, lambda d: d.get("role") == "passenger")

# Duplicate email
r = requests.post(f"{BASE}/auth/register", json={
    "name": "Test Passenger", "email": f"testpass_{RUN_ID}@x.com", "password": "pass1234"
})
check("POST /auth/register  (duplicate email blocked)", r, 400)

# Register driver
r = requests.post(f"{BASE}/auth/register", json={
    "name": "Test Driver", "email": f"testdriver_{RUN_ID}@x.com", "password": "pass1234", "role": "driver"
})
check("POST /auth/register  (driver)", r, 201)

# Register admin via seed account
r = requests.post(f"{BASE}/auth/register", json={
    "name": "Admin", "email": f"admin_{RUN_ID}@test.com", "password": "admin1234", "role": "passenger"
})
check("POST /auth/register  (admin seed account)", r, 201)

section("Auth — Login")

r = requests.post(f"{BASE}/auth/login", json={"email": f"testpass_{RUN_ID}@x.com", "password": "pass1234"})
data = check("POST /auth/login  (passenger)", r, 200, lambda d: "access_token" in d)
PASSENGER_TOKEN = data["access_token"] if data else None

r = requests.post(f"{BASE}/auth/login", json={"email": f"testdriver_{RUN_ID}@x.com", "password": "pass1234"})
data = check("POST /auth/login  (driver)", r, 200, lambda d: "access_token" in d)
DRIVER_TOKEN = data["access_token"] if data else None

r = requests.post(f"{BASE}/auth/login", json={"email": "testpass@x.com", "password": "wrongpass"})
check("POST /auth/login  (wrong password blocked)", r, 401)

r = requests.post(f"{BASE}/auth/login", json={"email": "nobody@x.com", "password": "pw"})
check("POST /auth/login  (unknown email blocked)", r, 401)

section("Auth — Profile")

P_HDR = {"Authorization": f"Bearer {PASSENGER_TOKEN}"}
D_HDR = {"Authorization": f"Bearer {DRIVER_TOKEN}"}

r = requests.get(f"{BASE}/auth/me", headers=P_HDR)
data = check("GET /auth/me  (passenger)", r, 200, lambda d: "testpass" in d.get("email", ""))
PASSENGER_ID = data["id"] if data else None

r = requests.patch(f"{BASE}/auth/me", json={"name": "Updated Name", "phone": "0501234567"}, headers=P_HDR)
check("PATCH /auth/me  (update name+phone)", r, 200, lambda d: d.get("name") == "Updated Name")

r = requests.get(f"{BASE}/auth/me")
check("GET /auth/me  (no token blocked)", r, 401)

# ── vehicles (need admin — promote our test admin) ────────────────────────────

section("Vehicles — Setup")

# Directly hit DB to make admin (seed script workaround since we have no admin token yet)
# Use seed_db admin credentials
r = requests.post(f"{BASE}/auth/login", json={"email": "admin@smartrouteai.local", "password": "admin1234"})
if r.status_code == 200:
    ADMIN_TOKEN = r.json()["access_token"]
    A_HDR = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
    print(f"  {PASS} Using seeded admin account")
    results["passed"] += 1
else:
    # Seed DB first
    print(f"  {WARN} No seeded admin found — run seed_db.py first for vehicle tests")
    results["warnings"] += 1
    ADMIN_TOKEN = None
    A_HDR = {}

section("Vehicles — CRUD")

if ADMIN_TOKEN:
    r = requests.post(f"{BASE}/vehicle/", json={
        "license_plate": f"TEST-{RUN_ID}-1", "capacity": 8, "status": "idle", "lat": 25.2048, "lng": 55.2708
    }, headers=A_HDR)
    data = check("POST /vehicle/  (create)", r, 201, lambda d: "TEST" in d.get("license_plate",""))
    VEHICLE_ID = data["id"] if data else None

    r = requests.post(f"{BASE}/vehicle/", json={
        "license_plate": f"TEST-{RUN_ID}-1", "capacity": 8
    }, headers=A_HDR)
    check("POST /vehicle/  (duplicate plate blocked)", r, 400)

    r = requests.post(f"{BASE}/vehicle/", json={
        "license_plate": f"TEST-{RUN_ID}-2", "capacity": 6, "status": "idle", "lat": 25.21, "lng": 55.28
    }, headers=A_HDR)
    check("POST /vehicle/  (create second)", r, 201)
else:
    VEHICLE_ID = None

r = requests.get(f"{BASE}/vehicle/", headers=P_HDR)
check("GET /vehicle/  (list)", r, 200, lambda d: isinstance(d, list))

r = requests.get(f"{BASE}/vehicle/idle", headers=P_HDR)
check("GET /vehicle/idle  (not shadowed by /{id})", r, 200, lambda d: isinstance(d, list))

r = requests.post(f"{BASE}/vehicle/", json={"license_plate": "NOPERM", "capacity": 4}, headers=P_HDR)
check("POST /vehicle/  (passenger blocked)", r, 403)

if VEHICLE_ID:
    r = requests.patch(f"{BASE}/vehicle/{VEHICLE_ID}", json={"lat": 25.22, "lng": 55.29}, headers=D_HDR)
    check(f"PATCH /vehicle/{VEHICLE_ID}  (driver update location)", r, 200)
else:
    print(f"  {WARN} VEHICLE_ID not available — skipping PATCH vehicle")
    results["warnings"] += 1

# ── rides ────────────────────────────────────────────────────────────────────

section("Rides")

r = requests.post(f"{BASE}/rides/request", json={
    "pickup_lat": 25.2048, "pickup_lng": 55.2708,
    "dest_lat": 25.1972, "dest_lng": 55.2796,
    "pickup_label": "Dubai Mall", "destination_label": "Airport"
}, headers=P_HDR)
data = check("POST /rides/request  (create)", r, 201, lambda d: d.get("status") == "pending")
RIDE_ID = data["id"] if data else None

# Create a few more rides for clustering
for i in range(4):
    requests.post(f"{BASE}/rides/request", json={
        "pickup_lat": 25.2048 + i * 0.001, "pickup_lng": 55.2708 + i * 0.001,
        "dest_lat": 25.20, "dest_lng": 55.28,
    }, headers=P_HDR)

r = requests.get(f"{BASE}/rides/my-rides", headers=P_HDR)
check("GET /rides/my-rides  (own rides)", r, 200, lambda d: isinstance(d, list) and len(d) >= 1)

r = requests.get(f"{BASE}/rides/{RIDE_ID}", headers=P_HDR)
check(f"GET /rides/{RIDE_ID}  (by id)", r, 200)

r = requests.get(f"{BASE}/rides/", headers=P_HDR)
check("GET /rides/  (passenger blocked)", r, 403)

r = requests.get(f"{BASE}/rides/", headers=D_HDR)
check("GET /rides/  (driver allowed)", r, 200, lambda d: isinstance(d, list))

r = requests.get(f"{BASE}/rides/?status=pending", headers=D_HDR)
check("GET /rides/?status=pending  (filter)", r, 200)

r = requests.get(f"{BASE}/rides/?status=invalid_status", headers=D_HDR)
check("GET /rides/?status=invalid_status  (bad status blocked)", r, 400)

r = requests.patch(f"{BASE}/rides/{RIDE_ID}/status", json={"status": "cancelled"}, headers=P_HDR)
check(f"PATCH /rides/{RIDE_ID}/status  (cancel own ride)", r, 200, lambda d: d.get("status") == "cancelled")

r = requests.patch(f"{BASE}/rides/{RIDE_ID}/status", json={"status": "bad_status"}, headers=D_HDR)
check("PATCH /rides/{id}/status  (invalid status blocked)", r, 400)

# ── clustering ───────────────────────────────────────────────────────────────

section("Clustering")

r = requests.post(f"{BASE}/cluster/run", json={"resolution": 9, "min_cluster_size": 2}, headers=D_HDR)
data = check("POST /cluster/run  (driver trigger)", r, 201, lambda d: "cluster_run_id" in d or d.get("status") in ("clustered", "no_pending_requests"))
CLUSTER_RUN_ID = data.get("cluster_run_id") if data else None

r = requests.post(f"{BASE}/cluster/run", json={"resolution": 9, "min_cluster_size": 2}, headers=P_HDR)
check("POST /cluster/run  (passenger blocked)", r, 403)

r = requests.get(f"{BASE}/cluster/history", headers=D_HDR)
check("GET /cluster/history", r, 200, lambda d: isinstance(d.get("runs"), list))

if CLUSTER_RUN_ID:
    r = requests.get(f"{BASE}/cluster/history/{CLUSTER_RUN_ID}", headers=D_HDR)
    check(f"GET /cluster/history/{CLUSTER_RUN_ID}", r, 200)

# ── route optimization ───────────────────────────────────────────────────────

section("Route Optimization")

if ADMIN_TOKEN:
    # Get current virtual stops
    r = requests.get(f"{BASE}/rides/", headers=D_HDR)
    # Get idle vehicles
    r = requests.get(f"{BASE}/vehicle/idle", headers=D_HDR)
    idle_vehicles = r.json() if r.status_code == 200 else []
    vehicle_ids = [v["id"] for v in idle_vehicles[:2]]

    # Get virtual stops from cluster history
    r = requests.get(f"{BASE}/cluster/history", headers=D_HDR)
    cluster_data = r.json()
    stop_ids = []
    if cluster_data.get("runs"):
        for run in cluster_data["runs"]:
            summary = run.get("cluster_summary") or []
            for s in summary:
                if s.get("virtual_stop_id"):
                    stop_ids.append(s["virtual_stop_id"])
    stop_ids = list(set(stop_ids))[:5]

    if vehicle_ids and stop_ids:
        r = requests.post(f"{BASE}/route/optimize", json={
            "vehicle_ids": vehicle_ids,
            "virtual_stop_ids": stop_ids,
            "depot_lat": 25.2048,
            "depot_lng": 55.2708,
            "source_cluster_run_id": CLUSTER_RUN_ID,
        }, headers=A_HDR)
        data = check("POST /route/optimize  (with stops)", r, 200, lambda d: d.get("status") in ("solved", "no_solution", "no_virtual_stops"))
        ROUTE_ID = data["routes"][0]["route_id"] if data and data.get("routes") else None
    else:
        print(f"  {WARN} No vehicles/stops available — skipping route optimize")
        results["warnings"] += 1
        ROUTE_ID = None

    r = requests.post(f"{BASE}/route/optimize", json={
        "vehicle_ids": [], "virtual_stop_ids": [],
        "depot_lat": 25.2, "depot_lng": 55.2
    }, headers=A_HDR)
    check("POST /route/optimize  (empty vehicle list blocked)", r, 400)

else:
    ROUTE_ID = None
    print(f"  {WARN} Skipping route tests — no admin token")
    results["warnings"] += 1

r = requests.get(f"{BASE}/route/history", headers=D_HDR)
check("GET /route/history", r, 200, lambda d: isinstance(d.get("routes"), list))

# ── tracking ─────────────────────────────────────────────────────────────────

section("Tracking")

r = requests.get(f"{BASE}/tracking/feed", headers=D_HDR)
check("GET /tracking/feed  (driver)", r, 200, lambda d: "vehicles" in d and "events" in d)

r = requests.get(f"{BASE}/tracking/feed", headers=P_HDR)
check("GET /tracking/feed  (passenger blocked)", r, 403)

r = requests.get(f"{BASE}/tracking/events", headers=D_HDR)
check("GET /tracking/events", r, 200, lambda d: isinstance(d, list))

if VEHICLE_ID:
    r = requests.post(f"{BASE}/tracking/vehicles/{VEHICLE_ID}/location", json={
        "lat": 25.205, "lng": 55.271, "status": "en_route"
    }, headers=D_HDR)
    check(f"POST /tracking/vehicles/{VEHICLE_ID}/location  (GPS update)", r, 200,
          lambda d: abs(d.get("lat", 0) - 25.205) < 0.001)

    r = requests.post(f"{BASE}/tracking/vehicles/{VEHICLE_ID}/location", json={
        "lat": 25.205, "lng": 55.271
    }, headers=P_HDR)
    check("POST /tracking/vehicles/{id}/location  (passenger blocked)", r, 403)

    # Verify event was recorded
    r = requests.get(f"{BASE}/tracking/events?limit=5", headers=D_HDR)
    check("GET /tracking/events  (event recorded after GPS update)", r, 200,
          lambda d: len(d) > 0)
else:
    print(f"  {WARN} VEHICLE_ID not available — skipping GPS update tests")
    results["warnings"] += 1

# ── notifications ────────────────────────────────────────────────────────────

section("Notifications")

r = requests.get(f"{BASE}/notifications/", headers=P_HDR)
data = check("GET /notifications/  (list)", r, 200, lambda d: "notifications" in d and "unread_count" in d)
notif_id = data["notifications"][0]["id"] if data and data["notifications"] else None

r = requests.get(f"{BASE}/notifications/?unread_only=true", headers=P_HDR)
check("GET /notifications/?unread_only=true", r, 200)

r = requests.get(f"{BASE}/notifications/unread-count", headers=P_HDR)
check("GET /notifications/unread-count", r, 200, lambda d: "updated_count" in d)

if notif_id:
    r = requests.patch(f"{BASE}/notifications/{notif_id}/read", headers=P_HDR)
    check(f"PATCH /notifications/{notif_id}/read", r, 200, lambda d: d.get("notification", {}).get("is_read") is True)

r = requests.patch(f"{BASE}/notifications/read-all", headers=P_HDR)
check("PATCH /notifications/read-all", r, 200, lambda d: "updated_count" in d)

r = requests.get(f"{BASE}/notifications/", headers={"Authorization": "Bearer badtoken"})
check("GET /notifications/  (bad token blocked)", r, 401)

# ── analytics ────────────────────────────────────────────────────────────────

section("Analytics")

r = requests.get(f"{BASE}/analytics/overview", headers=D_HDR)
check("GET /analytics/overview  (driver)", r, 200, lambda d: "total_rides" in d)

r = requests.get(f"{BASE}/analytics/overview", headers=P_HDR)
check("GET /analytics/overview  (passenger blocked)", r, 403)

r = requests.get(f"{BASE}/analytics/daily?days=7", headers=D_HDR)
check("GET /analytics/daily?days=7", r, 200, lambda d: len(d.get("points", [])) == 7)

r = requests.get(f"{BASE}/analytics/daily?days=91", headers=D_HDR)
check("GET /analytics/daily?days=91  (days>90 blocked)", r, 400)

# ── demand prediction ────────────────────────────────────────────────────────

section("Demand Prediction")

r = requests.get(f"{BASE}/predict/demand?latitude=25.2048&longitude=55.2708", headers=P_HDR)
check("GET /predict/demand  (point)", r, 200, lambda d: "predicted_demand" in d and "method" in d)

r = requests.get(
    f"{BASE}/predict/heatmap?min_lat=25.1&min_lng=55.2&max_lat=25.3&max_lng=55.4",
    headers=P_HDR
)
check("GET /predict/heatmap  (bounding box)", r, 200, lambda d: "cells" in d)

r = requests.get(
    f"{BASE}/predict/heatmap?min_lat=25.3&min_lng=55.2&max_lat=25.1&max_lng=55.4",
    headers=P_HDR
)
check("GET /predict/heatmap  (inverted bbox blocked)", r, 400)

# ── jobs ─────────────────────────────────────────────────────────────────────

section("Background Jobs")

r = requests.get(f"{BASE}/jobs/status", headers=D_HDR)
check("GET /jobs/status", r, 200, lambda d: "scheduler_running" in d)

r = requests.get(f"{BASE}/jobs/runs", headers=D_HDR)
check("GET /jobs/runs", r, 200, lambda d: isinstance(d, list))

r = requests.get(f"{BASE}/jobs/demand-snapshots", headers=D_HDR)
check("GET /jobs/demand-snapshots", r, 200, lambda d: isinstance(d, list))

r = requests.get(f"{BASE}/jobs/rebalance-suggestions", headers=D_HDR)
check("GET /jobs/rebalance-suggestions", r, 200, lambda d: isinstance(d, list))

r = requests.post(f"{BASE}/jobs/run/clustering", headers=D_HDR)
check("POST /jobs/run/clustering  (manual trigger)", r, 200)

r = requests.post(f"{BASE}/jobs/run/demand", headers=D_HDR)
check("POST /jobs/run/demand  (manual trigger)", r, 200)

r = requests.post(f"{BASE}/jobs/run/rebalance", headers=D_HDR)
check("POST /jobs/run/rebalance  (manual trigger)", r, 200)

r = requests.get(f"{BASE}/jobs/status", headers=P_HDR)
check("GET /jobs/status  (passenger blocked)", r, 403)

# ── summary ──────────────────────────────────────────────────────────────────

total = results["passed"] + results["failed"]
print(f"\n{'═'*55}")
print(f"  RESULTS: {results['passed']}/{total} passed  |  {results['failed']} failed  |  {results['warnings']} warnings")
print(f"{'═'*55}")

if results["failed"] > 0:
    sys.exit(1)
