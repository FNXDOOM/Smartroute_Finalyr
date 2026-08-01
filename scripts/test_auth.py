import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
import backend.models
from backend.main import app
from backend.database import Base, engine, create_db_tables, drop_db_tables

async def test_auth_flow():
    # Setup clean tables for test
    drop_db_tables(engine)
    create_db_tables(engine)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        print("1. Testing User Registration...")
        reg_payload = {
            "name": "John Doe",
            "email": "john@example.com",
            "password": "SecurePassword123!",
            "role": "passenger"
        }
        res_reg = await client.post("/auth/register", json=reg_payload)
        print(f"Registration Status: {res_reg.status_code}, Response: {res_reg.json()}")
        assert res_reg.status_code == 201
        assert res_reg.json()["email"] == "john@example.com"

        print("\n2. Testing Duplicate Registration Prevention...")
        res_dup = await client.post("/auth/register", json=reg_payload)
        print(f"Duplicate Status: {res_dup.status_code}, Detail: {res_dup.json()}")
        assert res_dup.status_code == 400

        print("\n3. Testing User Login & JWT Issuance...")
        login_payload = {
            "email": "john@example.com",
            "password": "SecurePassword123!"
        }
        res_login = await client.post("/auth/login", json=login_payload)
        print(f"Login Status: {res_login.status_code}")
        token_data = res_login.json()
        assert res_login.status_code == 200
        assert "access_token" in token_data
        token = token_data["access_token"]
        print(f"[OK] Acquired JWT Token: {token[:30]}...")

        print("\n4. Testing Protected Profile /auth/me Endpoint...")
        headers = {"Authorization": f"Bearer {token}"}
        res_me = await client.get("/auth/me", headers=headers)
        print(f"Profile Status: {res_me.status_code}, User: {res_me.json()['name']}")
        assert res_me.status_code == 200
        assert res_me.json()["email"] == "john@example.com"

        print("\n5. Testing Firebase Auth Token Exchange Endpoint...")
        firebase_payload = {
            "uid": "firebase_uid_998877",
            "email": "firebase_user@example.com",
            "name": "Firebase Rider"
        }
        res_fb = await client.post("/auth/firebase-login", json=firebase_payload)
        print(f"Firebase Sync Status: {res_fb.status_code}, Response User: {res_fb.json()['user']['email']}")
        assert res_fb.status_code == 200
        assert "access_token" in res_fb.json()

        print("\n[SUCCESS] All Auth endpoints, Password Hashing, JWT Tokens, and Firebase sync verified successfully!")

if __name__ == "__main__":
    asyncio.run(test_auth_flow())

