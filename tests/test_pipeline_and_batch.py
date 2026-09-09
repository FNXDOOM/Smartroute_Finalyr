import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from database import SessionLocal
from models.user import User
from models.vehicle import Vehicle
from models.ride_request import RideRequest
from services.background_jobs import run_auto_dispatch_pipeline


def test_auto_dispatch_pipeline_groups_and_assigns_rides():
    """Pipeline test: cluster, route, assign 3 rides."""
    db = SessionLocal()
    try:
        # Create test user if missing
        user = db.query(User).filter(User.email == "pipeline_tester@example.com").first()
        if not user:
            user = User(
                clerk_user_id="test_pipeline_user",
                email="pipeline_tester@example.com",
                name="Pipeline Tester",
                password_hash="test_hash",
                role="admin",
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        # Create idle test vehicle if missing
        vehicle = db.query(Vehicle).filter(Vehicle.license_plate == "KA-01-TEST-99").first()
        if not vehicle:
            vehicle = Vehicle(
                license_plate="KA-01-TEST-99",
                capacity=6,
                status="idle",
                lat=12.9784,
                lng=77.6408,
            )
            db.add(vehicle)
            db.commit()
            db.refresh(vehicle)
        else:
            vehicle.status = "idle"
            vehicle.assigned_route_id = None
            db.commit()

        # Clean any old test pending rides
        db.query(RideRequest).filter(RideRequest.user_id == user.id).delete()
        db.commit()

        # 3 rides within 20m in same H3 cell
        presets = [
            {"plat": 12.97190, "plng": 77.64124, "dlat": 12.9756, "dlng": 77.6066},
            {"plat": 12.97192, "plng": 77.64126, "dlat": 12.9749, "dlng": 77.6080},
            {"plat": 12.97194, "plng": 77.64120, "dlat": 12.9734, "dlng": 77.6075},
        ]
        created_rides = []
        for p in presets:
            r = RideRequest(
                user_id=user.id,
                pickup_lat=p["plat"],
                pickup_lng=p["plng"],
                dest_lat=p["dlat"],
                dest_lng=p["dlng"],
                status="pending",
                pickup_label="Test Pickup",
                destination_label="Test Dest",
                ride_option_id="swift-x",
                ride_option_name="SwiftX",
                ride_option_price="₹12–15",
            )
            db.add(r)
            created_rides.append(r)
        db.commit()

        for r in created_rides:
            db.refresh(r)
            assert r.status == "pending"

        # Run full dispatch pipeline
        result = run_auto_dispatch_pipeline(db, triggered_by_user_id=user.id, is_scheduled=False)

        assert result["clusters_formed"] >= 1, f"Expected >=1 cluster, got {result}"
        assert result["routes_optimized"] >= 1, f"Expected >=1 route, got {result}"
        assert result["assigned_rides"] >= 2, f"Expected >=2 rides assigned, got {result}"

        # Verify rides assigned
        assigned_count = 0
        for r in created_rides:
            db.refresh(r)
            if r.status == "assigned":
                assigned_count += 1
        assert assigned_count >= 2, f"Expected >=2 rides assigned, got {assigned_count}"

    finally:
        db.close()
