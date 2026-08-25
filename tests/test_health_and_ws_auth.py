from types import SimpleNamespace
import asyncio
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from main import app
from utils.auth_utils import get_websocket_token


def request(path: str) -> httpx.Response:
    async def run() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get(path)

    return asyncio.run(run())


def test_websocket_token_uses_bearer_subprotocol():
    websocket = SimpleNamespace(
        headers={"sec-websocket-protocol": "bearer, eyJ.test.token"},
        cookies={},
    )
    assert get_websocket_token(websocket) == "eyJ.test.token"


def test_websocket_query_tokens_are_rejected():
    websocket = SimpleNamespace(
        headers={},
        cookies={},
        query_params={"token": "eyJ.test.token"},
    )
    assert get_websocket_token(websocket) is None


def test_liveness_probe_is_public():
    response = request("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_protected_router_rejects_missing_authentication():
    response = request("/rides/my-rides")
    assert response.status_code == 401


def test_readiness_probe_checks_database():
    response = request("/health/ready")
    assert response.status_code == 200
    assert response.json()["database"] == "ok"
