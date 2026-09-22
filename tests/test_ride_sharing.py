import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from database import SessionLocal
from models.user import User
from models.ride_request import RideRequest
from models.virtual_stop import VirtualStop
from services.background_jobs import run_cluster_job
from services.carpool_matching import (
    find_cross_cell_corridor_groups,
    split_compatible_shared_group,
)


def _user(db):
    user = db.query(User).filter(User.email == "sharing_tester@example.com").first()
    if not user:
        user = User(
            clerk_user_id="test_sharing_user",
            email="sharing_tester@example.com",
            name="Sharing Tester",
            password_hash="test_hash",
            role="admin",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def _ride(db, user, plat, plng, is_shared):
    ride = RideRequest(
        user_id=user.id,
        pickup_lat=plat,
        pickup_lng=plng,
        dest_lat=12.9756,
        dest_lng=77.6066,
        status="pending",
        pickup_label="Test Pickup",
        destination_label="Test Dest",
        is_shared=is_shared,
    )
    db.add(ride)
    return ride


def test_shared_pool_is_capped_at_three_riders():
    requests = [
        type(
            "Request",
            (),
            {
                "id": index,
                "request_time": datetime.now(timezone.utc),
                "pickup_lat": 12.9719 + index * 0.00001,
                "pickup_lng": 77.6412 + index * 0.00001,
                "dest_lat": 12.9756,
                "dest_lng": 77.6066,
            },
        )()
        for index in range(4)
    ]

    groups = split_compatible_shared_group(requests)

    assert [len(group) for group in groups] == [3, 1]


def test_shared_pool_accepts_two_riders():
    requests = [
        type(
            "Request",
            (),
            {
                "id": index,
                "request_time": datetime.now(timezone.utc),
                "pickup_lat": 12.9719 + index * 0.00001,
                "pickup_lng": 77.6412 + index * 0.00001,
                "dest_lat": 12.9756,
                "dest_lng": 77.6066,
            },
        )()
        for index in range(2)
    ]

    groups = split_compatible_shared_group(requests)
    assert [len(group) for group in groups] == [2]


def test_cross_cell_corridor_match_keeps_each_rider_in_the_group():
    common_destination = (13.027276, 77.731848)
    requests = [
        type(
            "Request",
            (),
            {
                "id": 279,
                "request_time": datetime(2026, 9, 19, tzinfo=timezone.utc),
                "pickup_lat": 12.997038,
                "pickup_lng": 77.669131,
                "dest_lat": common_destination[0],
                "dest_lng": common_destination[1],
            },
        )(),
        type(
            "Request",
            (),
            {
                "id": 280,
                "request_time": datetime(2026, 9, 19, 0, 1, tzinfo=timezone.utc),
                "pickup_lat": 13.008374,
                "pickup_lng": 77.69529,
                "dest_lat": common_destination[0],
                "dest_lng": common_destination[1],
            },
        )(),
    ]

    groups, matched_ids = find_cross_cell_corridor_groups(requests)

    assert [len(group) for group in groups] == [2]
    assert matched_ids == {279, 280}


def test_corridor_matched_riders_share_one_cluster():
    """Riders the corridor pass pools must end up in a single cluster.

    The matcher returns a group of two, but the job assigned each member its own
    cluster id, so they were dispatched as separate one-passenger routes and the
    corridor match never became a carpool. Coordinates are a real production pair:
    857 m apart at pickup, identical destination.
    """
    db = SessionLocal()
    user_id = None
    try:
        user = _user(db)
        user_id = user.id
        db.query(RideRequest).filter(RideRequest.user_id == user_id).delete()
        db.commit()

        riders = []
        for plat, plng in ((12.99704, 77.66913), (13.00039, 77.67625)):
            ride = RideRequest(
                user_id=user.id,
                pickup_lat=plat,
                pickup_lng=plng,
                dest_lat=13.02728,
                dest_lng=77.73185,
                status="pending",
                pickup_label="Test Pickup",
                destination_label="Test Dest",
                is_shared=True,
            )
            db.add(ride)
            riders.append(ride)
        db.commit()

        assert [len(group) for group in find_cross_cell_corridor_groups(riders)[0]] == [2], (
            "fixture must be a corridor match, otherwise this tests nothing"
        )

        run_cluster_job(db)

        for ride in riders:
            db.refresh(ride)
            assert ride.status == "clustered", "corridor rider %s was not clustered" % ride.id
        assert len({ride.cluster_id for ride in riders}) == 1, (
            "corridor-matched riders must share one cluster, got %s"
            % [ride.cluster_id for ride in riders]
        )
        assert len({ride.virtual_stop_id for ride in riders}) == len(riders), (
            "each rider still needs a dedicated pickup stop"
        )
    finally:
        if user_id is not None:
            db.query(RideRequest).filter(RideRequest.user_id == user_id).delete()
            db.commit()
        db.close()


def test_manual_cluster_run_keeps_the_carpool_stage_in_step():
    """POST /cluster/run wrote `status` by hand, so a shared ride clustered
    through it was left with carpool_status NULL forever — the two axes only
    stay in lockstep if every writer advances both."""
    from routers.cluster import run_clustering
    from schemas.cluster import ClusterTriggerRequest

    db = SessionLocal()
    user_id = None
    stop_ids = []
    try:
        user = _user(db)
        user_id = user.id
        db.query(RideRequest).filter(RideRequest.user_id == user_id).delete()
        db.commit()

        riders = [
            _ride(db, user, 12.97250, 77.64200, True),
            _ride(db, user, 12.97252, 77.64202, True),
        ]
        db.commit()

        run_clustering(
            ClusterTriggerRequest(resolution=9, min_cluster_size=2), db=db, current_user=user, h3_index=None
        )

        for ride in riders:
            db.refresh(ride)
            assert ride.status == "clustered", "ride %s was not clustered" % ride.id
            assert ride.carpool_status == "clustered", (
                "ride %s advanced its coarse status but not its carpool stage" % ride.id
            )
            stop_ids.append(ride.virtual_stop_id)
    finally:
        if user_id is not None:
            db.query(RideRequest).filter(RideRequest.user_id == user_id).delete()
            db.commit()
        if stop_ids:
            db.query(VirtualStop).filter(VirtualStop.id.in_([s for s in stop_ids if s])).delete(
                synchronize_session=False
            )
            db.commit()
        db.close()


def test_private_rides_never_pool_and_shared_rides_do():
    """Shared riders pool into one cluster but each keeps a dedicated stop."""
    db = SessionLocal()
    user_id = None
    try:
        user = _user(db)
        user_id = user.id
        db.query(RideRequest).filter(RideRequest.user_id == user_id).delete()
        db.commit()

        private = [
            _ride(db, user, 12.97190, 77.64124, False),
            _ride(db, user, 12.97192, 77.64126, False),
        ]
        shared = [
            _ride(db, user, 12.97250, 77.64200, True),
            _ride(db, user, 12.97252, 77.64202, True),
            _ride(db, user, 12.97254, 77.64198, True),
        ]
        db.commit()

        run_cluster_job(db)

        for ride in private + shared:
            db.refresh(ride)
            assert ride.status == "clustered", "ride %s not clustered" % ride.id
            assert ride.virtual_stop_id is not None

        private_stops = {ride.virtual_stop_id for ride in private}
        assert len(private_stops) == len(private), "private rides must not share a stop"

        # Riders pooled together still keep a separate pickup stop each.
        shared_stops = {ride.virtual_stop_id for ride in shared}
        assert len(shared_stops) == len(shared), (
            "every shared rider needs a dedicated stop, got %s" % shared_stops
        )
        assert len({ride.cluster_id for ride in shared}) == 1, (
            "nearby shared riders should still form one pool"
        )
    finally:
        # The dispatch job reads every clustered ride in the database, so
        # leaving these behind would break unrelated tests (and the next run).
        if user_id is not None:
            db.query(RideRequest).filter(RideRequest.user_id == user_id).delete()
            db.commit()
        db.close()
