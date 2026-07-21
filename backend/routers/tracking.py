import asyncio
import json
import random
from typing import List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        dead = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                dead.append(connection)
        for d in dead:
            self.active_connections.remove(d)


manager = ConnectionManager()

# Shared task handle so we can cancel if needed
_simulation_task = None


async def simulate_gps_updates():
    """Background task: broadcasts simulated vehicle GPS updates every 2s."""
    vehicles = [
        {"id": "V1", "lat": 12.9716, "lng": 77.5946},  # Bangalore
        {"id": "V2", "lat": 12.9784, "lng": 77.6408},
        {"id": "V3", "lat": 12.9352, "lng": 77.6245},
    ]
    while True:
        for v in vehicles:
            v["lat"] += random.uniform(-0.002, 0.002)
            v["lng"] += random.uniform(-0.002, 0.002)

        payload = json.dumps({"type": "update", "vehicles": vehicles})
        await manager.broadcast(payload)
        await asyncio.sleep(2)


def start_simulation():
    """Called from the app lifespan to launch the background GPS task."""
    global _simulation_task
    _simulation_task = asyncio.create_task(simulate_gps_updates())


@router.websocket("/ws/tracking")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive; actual data is pushed by the simulation task
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
