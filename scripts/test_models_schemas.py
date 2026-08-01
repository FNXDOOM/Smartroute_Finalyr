import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.schemas.user import UserCreate, UserResponse, UserLogin, Token
from backend.schemas.ride_request import RideRequestCreate, RideRequestResponse
from backend.schemas.vehicle import VehicleCreate, VehicleResponse
from backend.schemas.virtual_stop import VirtualStopCreate, VirtualStopResponse
from backend.schemas.route import VRPRequest, OptimizedRouteResponse
from backend.schemas.cluster import ClusterTriggerRequest, ClusterResultResponse

from backend.models.user import User
from backend.models.vehicle import Vehicle
from backend.models.ride_request import RideRequest
from backend.models.virtual_stop import VirtualStop

def test_models_and_schemas():
    print("Testing Pydantic Schemas...")
    
    # 1. User
    user_in = UserCreate(name="Alice", email="alice@example.com", password="secretpassword", role="passenger")
    print(f"[OK] UserCreate Schema: {user_in.model_dump()}")
    
    # 2. Ride Request
    ride_in = RideRequestCreate(pickup_lat=12.9716, pickup_lng=77.5946, dest_lat=12.9352, dest_lng=77.6245)
    print(f"[OK] RideRequestCreate Schema: {ride_in.model_dump()}")
    
    # 3. Vehicle
    vehicle_in = VehicleCreate(license_plate="KA-01-EA-1234", capacity=6, status="idle", lat=12.9716, lng=77.5946)
    print(f"[OK] VehicleCreate Schema: {vehicle_in.model_dump()}")
    
    # 4. Virtual Stop
    stop_in = VirtualStopCreate(cluster_id=1, h3_index="8928308280fffff", lat=12.9720, lng=77.5950, passenger_count=3)
    print(f"[OK] VirtualStopCreate Schema: {stop_in.model_dump()}")
    
    # 5. Route
    vrp_in = VRPRequest(vehicle_ids=[1], virtual_stop_ids=[1, 2], depot_lat=12.97, depot_lng=77.59)
    print(f"[OK] VRPRequest Schema: {vrp_in.model_dump()}")

    print("\nTesting SQLAlchemy ORM Model Definitions...")
    assert User.__tablename__ == "users"
    assert Vehicle.__tablename__ == "vehicles"
    assert RideRequest.__tablename__ == "ride_requests"
    assert VirtualStop.__tablename__ == "virtual_stops"
    
    print("[SUCCESS] All ORM models & Pydantic schemas validated successfully!")

if __name__ == "__main__":
    test_models_and_schemas()
