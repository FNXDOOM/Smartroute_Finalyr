from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from backend.database import create_db_tables, drop_db_tables, get_db
from backend.models import *  # noqa: F401,F403 - register ORM models
from backend.models.cluster_run import ClusterRun
from backend.models.notification import Notification
from backend.models.ride_request import RideRequest
from backend.models.route_plan import RoutePlan
from backend.models.tracking_event import TrackingEvent
from backend.models.user import User
from backend.models.vehicle import Vehicle
from backend.models.virtual_stop import VirtualStop
from backend.services.background_jobs import run_cluster_job
from backend.services.clustering.h3_partitioner import get_h3_index
from backend.services.notifications import create_notification, create_notifications_for_users
from backend.routers.route import optimize_routes
from backend.schemas.route import VRPRequest
from backend.utils.auth_utils import hash_password


CITY_PRESETS: Dict[str, Tuple[float, float]] = {
    "bengaluru": (12.9716, 77.5946),
    "new_york": (40.7128, -74.0060),
    "london": (51.5074, -0.1278),
}


def _point(rng: random.Random, center_lat: float, center_lng: float, spread: float = 0.02) -> Tuple[float, float]:
    return (
        center_lat + rng.uniform(-spread, spread),
        center_lng + rng.uniform(-spread, spread),
    )


def _get_or_create_user(db, *, name: str, email: str, password: str, role: str) -> User:
    user = db.query(User).filter(User.email == email).first()
    if user:
        return user
    user = User(name=name, email=email, password_hash=hash_password(password), role=role)
    db.add(user)
    db.flush()
    return user


def _get_or_create_vehicle(db, *, license_plate: str, capacity: int, lat: float, lng: float) -> Vehicle:
    vehicle = db.query(Vehicle).filter(Vehicle.license_plate == license_plate).first()
    if vehicle:
        vehicle.capacity = capacity
        vehicle.lat = lat
        vehicle.lng = lng
        vehicle.status = "idle"
        return vehicle
    vehicle = Vehicle(
        license_plate=license_plate,
        capacity=capacity,
        status="idle",
        lat=lat,
        lng=lng,
    )
    db.add(vehicle)
    db.flush()
    return vehicle


def _seed_ride_requests(
    db,
    *,
    passengers: List[User],
    rng: random.Random,
    city_center: Tuple[float, float],
    count: int,
    start_hours_ago: int,
    status: str = "pending",
    pickup_spread: float = 0.0015,
) -> List[RideRequest]:
    rides: List[RideRequest] = []
    for index in range(count):
        passenger = passengers[index % len(passengers)]
        pickup_lat, pickup_lng = _point(rng, city_center[0], city_center[1], spread=pickup_spread)
        dest_lat, dest_lng = _point(rng, city_center[0] + 0.01, city_center[1] + 0.01, spread=0.025)
        request = RideRequest(
            user_id=passenger.id,
            pickup_lat=pickup_lat,
            pickup_lng=pickup_lng,
            dest_lat=dest_lat,
            dest_lng=dest_lng,
            status=status,
            h3_index=get_h3_index(pickup_lat, pickup_lng, resolution=9),
            request_time=datetime.utcnow() - timedelta(hours=start_hours_ago + index),
        )
        db.add(request)
        db.flush()
        create_notification(
            db,
            user_id=passenger.id,
            notification_type="ride_requested",
            title="Demo ride created",
            message=f"Demo ride request #{request.id} has been created for your test dataset.",
            related_entity_type="ride_request",
            related_entity_id=request.id,
            metadata={"seeded": True, "status": status},
            broadcast=False,
        )
        rides.append(request)
    return rides


def _seed_completed_history(
    db,
    *,
    passengers: List[User],
    rng: random.Random,
    city_center: Tuple[float, float],
    count: int,
) -> List[RideRequest]:
    rides: List[RideRequest] = []
    for index in range(count):
        passenger = passengers[index % len(passengers)]
        pickup_lat, pickup_lng = _point(rng, city_center[0], city_center[1], spread=0.03)
        dest_lat, dest_lng = _point(rng, city_center[0] + 0.015, city_center[1] + 0.015, spread=0.03)
        status = "completed" if index % 2 == 0 else "cancelled"
        request = RideRequest(
            user_id=passenger.id,
            pickup_lat=pickup_lat,
            pickup_lng=pickup_lng,
            dest_lat=dest_lat,
            dest_lng=dest_lng,
            status=status,
            h3_index=get_h3_index(pickup_lat, pickup_lng, resolution=9),
            request_time=datetime.utcnow() - timedelta(days=3, hours=index),
        )
        db.add(request)
        db.flush()
        create_notification(
            db,
            user_id=passenger.id,
            notification_type=f"ride_{status}",
            title=f"Historical ride {status}",
            message=f"Historical ride request #{request.id} was seeded as {status}.",
            related_entity_type="ride_request",
            related_entity_id=request.id,
            metadata={"seeded": True, "status": status},
            broadcast=False,
        )
        rides.append(request)
    return rides


def _emit_tracking_sample(db, *, vehicle: Vehicle, current_user: User, route_passenger_user_ids: List[int], lat: float, lng: float):
    vehicle.lat = lat
    vehicle.lng = lng
    vehicle.status = "en_route"
    event = TrackingEvent(
        vehicle_id=vehicle.id,
        event_type="vehicle_location_update",
        status=vehicle.status,
        lat=lat,
        lng=lng,
        payload={"seeded": True},
    )
    db.add(event)
    db.flush()

    create_notification(
        db,
        user_id=current_user.id,
        notification_type="vehicle_location_logged",
        title="Seeded tracking sample",
        message=f"Seeded location update stored for vehicle {vehicle.license_plate}.",
        related_entity_type="vehicle",
        related_entity_id=vehicle.id,
        metadata={"seeded": True, "event_id": event.id},
        broadcast=False,
    )
    if route_passenger_user_ids:
        create_notifications_for_users(
            db,
            user_ids=route_passenger_user_ids,
            notification_type="vehicle_tracking_update",
            title="Seeded tracking update",
            message=f"Vehicle {vehicle.license_plate} received a live tracking sample.",
            related_entity_type="vehicle",
            related_entity_id=vehicle.id,
            metadata={"seeded": True, "event_id": event.id},
            broadcast=False,
        )


def _jsonable(value):
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value


def _create_manual_demo_clusters(
    db,
    *,
    admin: User,
    rides: List[RideRequest],
    city_center: Tuple[float, float],
) -> Dict:
    hotspot_offsets = [(-0.01, -0.01), (0.0, 0.012), (0.014, -0.008)]
    cluster_summary = []
    next_cluster_id = (db.query(VirtualStop.cluster_id).order_by(VirtualStop.cluster_id.desc()).first() or (0,))[0] + 1

    for index, offset in enumerate(hotspot_offsets):
        cluster_rides = rides[index * 8 : (index + 1) * 8]
        if not cluster_rides:
            continue

        cluster_lat = city_center[0] + offset[0]
        cluster_lng = city_center[1] + offset[1]
        virtual_stop = VirtualStop(
            cluster_id=next_cluster_id,
            h3_index=get_h3_index(cluster_lat, cluster_lng, resolution=9),
            lat=cluster_lat,
            lng=cluster_lng,
            snapped_node_id=f"seeded-{next_cluster_id}",
            passenger_count=len(cluster_rides),
        )
        db.add(virtual_stop)
        db.flush()

        ride_ids = []
        for ride in cluster_rides:
            ride.cluster_id = next_cluster_id
            ride.virtual_stop_id = virtual_stop.id
            ride.status = "clustered"
            ride_ids.append(ride.id)

        cluster_summary.append(
            {
                "cluster_id": next_cluster_id,
                "h3_index": virtual_stop.h3_index,
                "ride_request_ids": ride_ids,
                "virtual_stop_id": virtual_stop.id,
                "virtual_stop_lat": virtual_stop.lat,
                "virtual_stop_lng": virtual_stop.lng,
                "passenger_count": len(cluster_rides),
                "snapped_node_id": virtual_stop.snapped_node_id,
                "seeded_manual": True,
            }
        )
        next_cluster_id += 1

    cluster_run = ClusterRun(
        run_uuid=f"seed-manual-{admin.id}-{datetime.utcnow().timestamp():.0f}",
        resolution=9,
        min_cluster_size=3,
        status="clustered",
        total_processed_requests=len(rides),
        clusters_formed=len(cluster_summary),
        noise_requests_count=0,
        created_by_user_id=admin.id,
        cluster_summary=cluster_summary,
    )
    db.add(cluster_run)
    db.flush()
    return {
        "job_run_id": None,
        "cluster_run_id": cluster_run.id,
        "processed_requests": len(rides),
        "clusters_formed": len(cluster_summary),
        "noise_requests_count": 0,
        "manual": True,
    }


def seed_database(city: str, reset: bool = False):
    city_key = city.lower().strip()
    if city_key not in CITY_PRESETS:
        raise ValueError(f"Unsupported city '{city}'. Choose one of: {', '.join(CITY_PRESETS)}")

    if reset:
        drop_db_tables()
    create_db_tables()

    rng = random.Random(42)
    center_lat, center_lng = CITY_PRESETS[city_key]

    db = next(get_db())
    try:
        admin = _get_or_create_user(
            db,
            name="Admin User",
            email="admin@smartrouteai.local",
            password="admin1234",
            role="admin",
        )
        drivers = [
            _get_or_create_user(
                db,
                name=f"Driver {index}",
                email=f"driver{index}@smartrouteai.local",
                password="driver1234",
                role="driver",
            )
            for index in range(1, 3)
        ]
        passengers = [
            _get_or_create_user(
                db,
                name=f"Passenger {index}",
                email=f"passenger{index}@smartrouteai.local",
                password="passenger1234",
                role="passenger",
            )
            for index in range(1, 11)
        ]

        vehicles = [
            _get_or_create_vehicle(
                db,
                license_plate=f"SR-{100 + index}",
                capacity=10,
                lat=center_lat + rng.uniform(-0.01, 0.01),
                lng=center_lng + rng.uniform(-0.01, 0.01),
            )
            for index in range(1, 5)
        ]

        pending_rides: List[RideRequest] = []
        hotspot_offsets = [(-0.01, -0.01), (0.0, 0.012), (0.014, -0.008)]
        for hotspot_index, offset in enumerate(hotspot_offsets):
            hotspot_center = (center_lat + offset[0], center_lng + offset[1])
            pending_rides.extend(
                _seed_ride_requests(
                    db,
                    passengers=passengers,
                    rng=rng,
                    city_center=hotspot_center,
                    count=8,
                    start_hours_ago=hotspot_index * 2,
                    status="pending",
                    pickup_spread=0.0012,
                )
            )

        _seed_completed_history(
            db,
            passengers=passengers,
            rng=rng,
            city_center=(center_lat, center_lng),
            count=6,
        )

        db.commit()

        cluster_result = run_cluster_job(
            db,
            resolution=9,
            min_cluster_size=3,
            triggered_by_user_id=admin.id,
            is_scheduled=False,
        )

        if not db.query(VirtualStop).count():
            cluster_result = _create_manual_demo_clusters(
                db,
                admin=admin,
                rides=pending_rides,
                city_center=(center_lat, center_lng),
            )
            db.commit()

        route_payload = VRPRequest(
            vehicle_ids=[vehicle.id for vehicle in vehicles],
            virtual_stop_ids=[stop.id for stop in db.query(VirtualStop).order_by(VirtualStop.id.asc()).all()],
            depot_lat=center_lat,
            depot_lng=center_lng,
            source_cluster_run_id=cluster_result.get("cluster_run_id"),
        )
        try:
            route_result = optimize_routes(route_payload, db=db, current_user=admin)
        except Exception as exc:
            route_result = {"status": "route_failed", "error": str(exc)}

        db.commit()

        first_vehicle = db.query(Vehicle).order_by(Vehicle.id.asc()).first()
        route_plan = db.query(RoutePlan).order_by(RoutePlan.created_at.desc()).first()
        route_passenger_user_ids: List[int] = []
        if route_plan and route_plan.route_metadata and isinstance(route_plan.route_metadata, dict):
            stop_ids = route_plan.route_metadata.get("assigned_stop_ids", []) or []
            if stop_ids:
                virtual_stops = db.query(VirtualStop).filter(VirtualStop.id.in_(stop_ids)).all()
                for virtual_stop in virtual_stops:
                    route_passenger_user_ids.extend(request.user_id for request in virtual_stop.ride_requests)
        if first_vehicle:
            _emit_tracking_sample(
                db,
                vehicle=first_vehicle,
                current_user=admin,
                route_passenger_user_ids=sorted(set(route_passenger_user_ids)),
                lat=center_lat + 0.002,
                lng=center_lng + 0.002,
            )

        create_notification(
            db,
            user_id=admin.id,
            notification_type="seed_complete",
            title="Demo dataset seeded",
            message="SmartRouteAI demo data has been populated successfully.",
            related_entity_type="seed_job",
            related_entity_id=None,
            metadata={
                "city": city_key,
                "pending_rides": len(pending_rides),
                "vehicles": len(vehicles),
                "cluster_result": _jsonable(cluster_result),
                "route_result": _jsonable(route_result),
            },
            broadcast=False,
        )

        db.commit()

        return {
            "city": city_key,
            "admin_email": admin.email,
            "driver_emails": [driver.email for driver in drivers],
            "passenger_count": len(passengers),
            "vehicles": len(vehicles),
            "pending_rides": len(pending_rides),
            "cluster_result": _jsonable(cluster_result),
            "route_result": _jsonable(route_result),
        }
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Seed SmartRouteAI with realistic demo data")
    parser.add_argument("--city", default="bengaluru", choices=sorted(CITY_PRESETS.keys()))
    parser.add_argument("--reset", action="store_true", help="Drop and recreate all tables before seeding")
    args = parser.parse_args()

    result = seed_database(args.city, reset=args.reset)
    print(result)


if __name__ == "__main__":
    main()
