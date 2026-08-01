import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
import backend.models
from backend.main import app
from backend.database import Base, engine, create_db_tables, drop_db_tables


async def test_rides_flow():
    drop_db_tables(engine)
    create_db_tables(engine)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        print("1. Registering passenger user...")
        reg_res = await client.post("/auth/register", json={
            "name": "Bob Rider",
            "email": "bob@example.com",
            "password": "RiderPassword123!",
            "role": "passenger"
        })
        assert reg_res.status_code == 201
        
        login_res = await client.post("/auth/login", json={
            "email": "bob@example.com",
            "password": "RiderPassword123!"
        })
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("[OK] User authenticated and JWT acquired.")

        print("\n2. Submitting ride request (Bangalore City Center to Koramangala)...")
        ride_payload = {
            "pickup_lat": 12.9716,
            "pickup_lng": 77.5946,
            "dest_lat": 12.9352,
            "dest_lng": 77.6245
        }
        res_req = await client.post("/rides/request", json=ride_payload, headers=headers)
        print(f"Ride Request Status: {res_req.status_code}, Response: {res_req.json()}")
        assert res_req.status_code == 201
        ride_data = res_req.json()
        ride_id = ride_data["id"]
        assert ride_data["status"] == "pending"
        assert ride_data["h3_index"] is not None
        print(f"[OK] Ride #{ride_id} created with H3 spatial index: {ride_data['h3_index']}")

        print("\n3. Fetching user's ride history (/rides/my-rides)...")
        res_my = await client.get("/rides/my-rides", headers=headers)
        print(f"My Rides Count: {len(res_my.json())}")
        assert res_my.status_code == 200
        assert len(res_my.json()) == 1

        print("\n4. Getting single ride details (/rides/{id})...")
        res_detail = await client.get(f"/rides/{ride_id}", headers=headers)
        assert res_detail.status_code == 200
        assert res_detail.json()["id"] == ride_id

        print("\n5. Querying pending rides (/rides/?status=pending)...")
        res_list = await client.get("/rides/?status=pending", headers=headers)
        assert res_list.status_code == 200
        assert len(res_list.json()) == 1

        print("\n6. Updating ride status to 'clustered'...")
        res_update = await client.patch(f"/rides/{ride_id}/status", json={"status": "clustered"}, headers=headers)
        print(f"Updated Status: {res_update.json()['status']}")
        assert res_update.status_code == 200
        assert res_update.json()["status"] == "clustered"

        print("\n7. Cancelling ride request...")
        res_cancel = await client.delete(f"/rides/{ride_id}", headers=headers)
        print(f"Cancel Response: {res_cancel.json()}")
        assert res_cancel.status_code == 200

        print("\n[SUCCESS] Ride Request Endpoints verified 100% successfully!")


if __name__ == "__main__":
    asyncio.run(test_rides_flow())
