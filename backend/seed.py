"""
seed.py — populate all tables with realistic Bengaluru demo data.

Usage (from backend/ directory):
    python seed.py              # seed everything
    python seed.py --reset      # drop existing data first, then seed

The script is idempotent for vehicles, users and ride-option labels:
re-running without --reset will not duplicate those rows.
"""

import argparse
import random
import secrets
import sys
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

# ── bootstrap path ──────────────────────────────────────────────────────────
sys.path.insert(0, ".")
from database import SessionLocal, create_db_tables, engine
from models.user import User
from models.vehicle import Vehicle
from models.ride_request import RideRequest
from models.virtual_stop import VirtualStop
from models.cluster_run import ClusterRun
from models.notification import Notification
from models.tracking_event import TrackingEvent
from models.job_run import JobRun
from models.demand_snapshot import DemandSnapshot
from models.vehicle_rebalance_suggestion import VehicleRebalanceSuggestion

# ── constants ───────────────────────────────────────────────────────────────
random.seed(42)

# Key Bengaluru landmarks (lat, lng, label)
BENGALURU_LOCATIONS = [
    (12.9784, 77.6408, "Indiranagar Metro Station"),
    (12.9352, 77.6245, "Embassy TechVillage, ORR"),
    (12.9716, 77.5946, "Koramangala 5th Block"),
    (12.9141, 77.6101, "HSR Layout Sector 2"),
    (12.9850, 77.5533, "Malleshwaram 18th Cross"),
    (12.9698, 77.7499, "Whitefield, ITPL Main Road"),
    (12.9259, 77.6762, "Bellandur Lake Road"),
    (12.9010, 77.5855, "JP Nagar 7th Phase"),
    (13.0358, 77.5970, "Hebbal Flyover Junction"),
    (12.9279, 77.5510, "Banashankari BDA Complex"),
    (12.9569, 77.7011, "Marathahalli Bridge"),
    (12.9177, 77.6237, "Sarjapur Road, Wipro Gate"),
    (13.0067, 77.5963, "Sadashivanagar Circle"),
    (12.9800, 77.6300, "UB City Mall, Vittal Mallya Rd"),
    (12.9623, 77.5948, "BTM Layout 2nd Stage"),
    (12.9366, 77.5560, "Jayanagar 9th Block"),
    (13.0190, 77.6500, "Banaswadi Main Road"),
    (12.9947, 77.6945, "Mahadevapura Circle"),
    (12.9100, 77.6500, "Electronic City Phase 1"),
    (12.9450, 77.6820, "Kadubeesanahalli, ORR"),
]

RIDE_OPTIONS = [
    ("swift-x",    "SwiftX",    "₹12–15"),
    ("swift-xl",   "SwiftXL",   "₹18–22"),
    ("swift-lux",  "Lux Black", "₹32–40"),
    ("swift-moto", "Moto",      "₹6–9"),
]

VEHICLE_PLATES = [
    ("KA01AB1234", 4), ("KA02CD5678", 4), ("KA03EF9012", 6),
    ("KA04GH3456", 4), ("KA05IJ7890", 4), ("KA06KL2345", 6),
    ("KA07MN6789", 4), ("KA08OP0123", 4), ("KA09QR4567", 6),
    ("KA10ST8901", 4),
]

STATUSES = ["pending", "clustered", "assigned", "in_progress", "completed", "cancelled"]
STATUS_WEIGHTS = [0.15, 0.10, 0.10, 0.10, 0.45, 0.10]


# ── helpers ──────────────────────────────────────────────────────────────────
def jitter(lat: float, lng: float, radius: float = 0.02):
    return lat + random.uniform(-radius, radius), lng + random.uniform(-radius, radius)


def past(days: int = 0, hours: int = 0, minutes: int = 0) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days, hours=hours, minutes=minutes)


def fake_h3(lat: float, lng: float) -> str:
    """Deterministic fake H3 index based on truncated coords (good enough for demo)."""
    return f"8928308{abs(int(lat*100)):04d}{abs(int(lng*100)):04d}ff"


# ── seed functions ────────────────────────────────────────────────────────────
def seed_users(db: Session) -> list[User]:
    demo = [
        ("Arjun Sharma",   "arjun.sharma@demo.com",   "+91-98765-43210", "passenger"),
        ("Priya Nair",     "priya.nair@demo.com",     "+91-87654-32109", "passenger"),
        ("Karan Mehta",    "karan.mehta@demo.com",    "+91-76543-21098", "passenger"),
        ("Divya Reddy",    "divya.reddy@demo.com",    "+91-65432-10987", "passenger"),
        ("Rohit Kumar",    "rohit.kumar@demo.com",    "+91-54321-09876", "passenger"),
        ("Suresh Driver",  "suresh.driver@demo.com",  "+91-99887-76655", "driver"),
        ("Anil Driver",    "anil.driver@demo.com",    "+91-88776-65544", "driver"),
        ("Admin User",     "admin@smartroute.ai",     "+91-77665-54433", "admin"),
    ]
    users = []
    for name, email, phone, role in demo:
        existing = db.query(User).filter(User.email == email).first()
        if existing:
            users.append(existing)
            continue
        u = User(
            name=name, email=email, phone=phone, role=role,
            password_hash=secrets.token_urlsafe(32),
        )
        db.add(u)
        users.append(u)
    db.flush()
    print(f"  ✓ {len(users)} users")
    return users


def seed_vehicles(db: Session) -> list[Vehicle]:
    vehicles = []
    statuses = ["idle", "idle", "idle", "active", "active", "idle", "en_route", "idle", "idle", "idle"]
    for i, (plate, cap) in enumerate(VEHICLE_PLATES):
        existing = db.query(Vehicle).filter(Vehicle.license_plate == plate).first()
        if existing:
            vehicles.append(existing)
            continue
        base_loc = BENGALURU_LOCATIONS[i % len(BENGALURU_LOCATIONS)]
        lat, lng = jitter(base_loc[0], base_loc[1], 0.03)
        v = Vehicle(
            license_plate=plate, capacity=cap,
            status=statuses[i], lat=round(lat, 6), lng=round(lng, 6),
        )
        db.add(v)
        vehicles.append(v)
    db.flush()
    print(f"  ✓ {len(vehicles)} vehicles")
    return vehicles


def seed_rides(db: Session, users: list[User], n: int = 60) -> list[RideRequest]:
    passengers = [u for u in users if u.role == "passenger"]
    rides = []
    for i in range(n):
        user = random.choice(passengers)
        pickup = random.choice(BENGALURU_LOCATIONS)
        dest   = random.choice([l for l in BENGALURU_LOCATIONS if l != pickup])
        plat, plng = jitter(pickup[0], pickup[1], 0.005)
        dlat, dlng = jitter(dest[0], dest[1], 0.005)
        status = random.choices(STATUSES, STATUS_WEIGHTS)[0]
        opt = random.choice(RIDE_OPTIONS)
        days_ago = random.randint(0, 30)
        hours_ago = random.randint(0, 23)
        r = RideRequest(
            user_id=user.id,
            pickup_lat=round(plat, 6), pickup_lng=round(plng, 6),
            dest_lat=round(dlat, 6),   dest_lng=round(dlng, 6),
            pickup_label=pickup[2],    destination_label=dest[2],
            status=status,
            h3_index=fake_h3(plat, plng),
            ride_option_id=opt[0], ride_option_name=opt[1], ride_option_price=opt[2],
            request_time=past(days=days_ago, hours=hours_ago, minutes=random.randint(0, 59)),
        )
        db.add(r)
        rides.append(r)
    db.flush()
    print(f"  ✓ {len(rides)} ride requests")
    return rides


def seed_virtual_stops(db: Session, rides: list[RideRequest]) -> list[VirtualStop]:
    """Group pending/clustered rides into virtual stops."""
    pending = [r for r in rides if r.status in ("pending", "clustered")]
    stops = []
    cluster_id = 1
    # Group into batches of 2-4
    random.shuffle(pending)
    idx = 0
    while idx < len(pending):
        batch_size = random.randint(2, 4)
        batch = pending[idx:idx+batch_size]
        idx += batch_size
        if not batch:
            break
        avg_lat = sum(r.pickup_lat for r in batch) / len(batch)
        avg_lng = sum(r.pickup_lng for r in batch) / len(batch)
        stop = VirtualStop(
            cluster_id=cluster_id,
            h3_index=fake_h3(avg_lat, avg_lng),
            lat=round(avg_lat, 6), lng=round(avg_lng, 6),
            passenger_count=len(batch),
        )
        db.add(stop)
        db.flush()
        for r in batch:
            r.cluster_id = cluster_id
            r.virtual_stop_id = stop.id
        stops.append(stop)
        cluster_id += 1
    print(f"  ✓ {len(stops)} virtual stops")
    return stops


def seed_cluster_runs(db: Session, admin: User, rides: list[RideRequest]) -> list[ClusterRun]:
    runs = []
    for i in range(5):
        n_rides = random.randint(8, 20)
        n_clusters = random.randint(3, 8)
        summary = [
            {
                "cluster_id": j + 1,
                "h3_index": fake_h3(12.95 + j * 0.01, 77.60 + j * 0.01),
                "passenger_count": random.randint(2, 5),
                "virtual_stop_id": j + 1,
                "virtual_stop_lat": round(12.95 + j * 0.01 + random.uniform(-0.002, 0.002), 6),
                "virtual_stop_lng": round(77.60 + j * 0.01 + random.uniform(-0.002, 0.002), 6),
                "ride_request_ids": list(range(j * 3 + 1, j * 3 + 4)),
            }
            for j in range(n_clusters)
        ]
        run = ClusterRun(
            run_uuid=str(uuid.uuid4()),
            resolution=9,
            min_cluster_size=2,
            status="clustered" if i < 4 else "no_pending_requests",
            total_processed_requests=n_rides,
            clusters_formed=n_clusters,
            noise_requests_count=random.randint(0, 3),
            created_by_user_id=admin.id,
            cluster_summary=summary,
            created_at=past(days=i),
        )
        db.add(run)
        runs.append(run)
    db.flush()
    print(f"  ✓ {len(runs)} cluster runs")
    return runs


def seed_tracking_events(db: Session, vehicles: list[Vehicle]) -> None:
    events = []
    for v in vehicles:
        if not v.lat:
            continue
        for j in range(random.randint(3, 8)):
            lat, lng = jitter(v.lat, v.lng, 0.008)
            events.append(TrackingEvent(
                vehicle_id=v.id,
                event_type=random.choice(["vehicle_location_update", "vehicle_arrived", "vehicle_departed"]),
                status=v.status,
                lat=round(lat, 6), lng=round(lng, 6),
                payload={"speed_kmh": random.randint(10, 60), "heading": random.randint(0, 359)},
                created_at=past(hours=random.randint(0, 48), minutes=random.randint(0, 59)),
            ))
    for e in events:
        db.add(e)
    print(f"  ✓ {len(events)} tracking events")


def seed_notifications(db: Session, users: list[User], rides: list[RideRequest]) -> None:
    types = [
        ("ride_requested",      "Ride request received",     "Your ride request has been received and is pending dispatch."),
        ("ride_status_updated", "Ride status updated",       "Your ride has been assigned to a vehicle."),
        ("route_assigned",      "Route assigned",            "Your shared route has been optimised and a vehicle is on the way."),
        ("system",              "Welcome to SmartRoute AI",  "Your account is set up. Book your first ride!"),
    ]
    count = 0
    for user in users:
        for i, (ntype, title, msg) in enumerate(types[:random.randint(1, len(types))]):
            n = Notification(
                user_id=user.id,
                notification_type=ntype,
                title=title,
                message=msg,
                is_read=random.choice([True, True, False]),
                created_at=past(hours=random.randint(0, 72)),
            )
            db.add(n)
            count += 1
    print(f"  ✓ {count} notifications")


def seed_job_runs(db: Session, admin: User) -> list[JobRun]:
    jobs = []
    job_types = [
        ("cluster_job",  "clustering"),
        ("demand_job",   "demand"),
        ("rebalance_job","rebalance"),
    ]
    for i in range(12):
        jname, jtype = random.choice(job_types)
        started = past(hours=i * 4 + random.randint(0, 3))
        finished = started + timedelta(seconds=random.randint(2, 30))
        j = JobRun(
            job_name=jname,
            status=random.choices(["completed", "completed", "completed", "failed"], [0.7, 0.1, 0.1, 0.1])[0],
            triggered_by_user_id=admin.id if random.random() > 0.5 else None,
            is_scheduled=random.choice([True, False]),
            summary={"processed": random.randint(5, 40), "type": jtype},
            started_at=started,
            finished_at=finished,
        )
        db.add(j)
        jobs.append(j)
    db.flush()
    print(f"  ✓ {len(jobs)} job runs")
    return jobs


def seed_demand_snapshots(db: Session, job_runs: list[JobRun]) -> None:
    count = 0
    for job in job_runs[:5]:
        for loc in random.sample(BENGALURU_LOCATIONS, random.randint(4, 8)):
            lat, lng = jitter(loc[0], loc[1], 0.01)
            snap = DemandSnapshot(
                job_run_id=job.id,
                h3_index=fake_h3(lat, lng),
                lat=round(lat, 6), lng=round(lng, 6),
                lookback_days=30,
                historical_request_count=random.randint(1, 25),
                predicted_demand=round(random.uniform(1.0, 20.0), 2),
                model_name="heuristic",
                method="exponential_smoothing",
            )
            db.add(snap)
            count += 1
    print(f"  ✓ {count} demand snapshots")


def seed_rebalance_suggestions(db: Session, vehicles: list[Vehicle], job_runs: list[JobRun]) -> None:
    reasons = [
        "High demand predicted in this zone",
        "No vehicles within 2 km of cluster centroid",
        "Unbalanced fleet distribution detected",
    ]
    count = 0
    for v in vehicles[:5]:
        target = random.choice(BENGALURU_LOCATIONS)
        tlat, tlng = jitter(target[0], target[1], 0.01)
        sug = VehicleRebalanceSuggestion(
            vehicle_id=v.id,
            job_run_id=random.choice(job_runs).id,
            target_h3_index=fake_h3(tlat, tlng),
            target_lat=round(tlat, 6),
            target_lng=round(tlng, 6),
            score=round(random.uniform(0.5, 1.0), 3),
            reason=random.choice(reasons),
            created_at=past(hours=random.randint(1, 24)),
        )
        db.add(sug)
        count += 1
    print(f"  ✓ {count} rebalance suggestions")


# ── main ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Seed the SmartRoute AI database")
    parser.add_argument("--reset", action="store_true", help="Delete all existing data before seeding")
    args = parser.parse_args()

    print("🌱 SmartRoute AI — database seeder")
    print(f"   DB: {engine.url}\n")

    create_db_tables()

    db: Session = SessionLocal()
    try:
        if args.reset:
            print("⚠️  Resetting all data…")
            for table in [
                "vehicle_rebalance_suggestions", "demand_snapshots", "job_runs",
                "tracking_events", "notifications", "route_waypoints", "route_plans",
                "cluster_runs", "ride_requests", "virtual_stops", "vehicles", "users",
            ]:
                try:
                    db.execute(__import__("sqlalchemy").text(f"DELETE FROM {table}"))
                except Exception as e:
                    print(f"   (skip {table}: {e})")
            db.commit()
            print("   Done.\n")

        print("Seeding…")
        users    = seed_users(db)
        vehicles = seed_vehicles(db)
        admin    = next((u for u in users if u.role == "admin"), users[-1])

        rides    = seed_rides(db, users, n=60)
        seed_virtual_stops(db, rides)
        seed_cluster_runs(db, admin, rides)
        seed_tracking_events(db, vehicles)
        seed_notifications(db, users, rides)
        job_runs = seed_job_runs(db, admin)
        seed_demand_snapshots(db, job_runs)
        seed_rebalance_suggestions(db, vehicles, job_runs)

        db.commit()
        print("\n✅ Seeding complete!")
        print("   Passenger login: arjun.sharma@demo.com")
        print("   Driver login:    suresh.driver@demo.com")
        print("   Admin login:     admin@smartroute.ai")
        print("\n   Note: these are DB-only users. To log in via Clerk,")
        print("   sign up in the app — your Clerk account auto-provisions")
        print("   a DB user with role=passenger on first sign-in.")

    except Exception as e:
        db.rollback()
        print(f"\n❌ Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
