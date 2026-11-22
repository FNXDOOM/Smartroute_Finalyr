"""Standalone synthetic fleet feed. Run with uvicorn vehicle_demo:app."""

import asyncio
import math
import time

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI(title="SmartRoute vehicle demo")
CENTRE = (77.5946, 12.9716)
SPEEDS = {"bike": 8, "auto": 7, "car": 10, "suv": 10}
INTERVAL = 2
STOP = 1.5
CITY_METRES = (111_195 * math.cos(math.radians(CENTRE[1])), 111_195)

# Synthetic waypoints in metres; this feed needs neither a database nor OSRM.
TRIPS = tuple(
    tuple(
        (CENTRE[0] + (x + col * 480) / CITY_METRES[0],
         CENTRE[1] + (y + row * 390) / CITY_METRES[1])
        for x, y in ((0, 0), (120, 20), (140, 110), (230, 145), (310, 90))
    )
    for row in range(-1, 2)
    for col in range(-2, 2)
)
EPOCH = time.monotonic()


def track(coords, kind, elapsed):
    vectors = [
        ((b[0] - a[0]) * CITY_METRES[0], (b[1] - a[1]) * CITY_METRES[1])
        for a, b in zip(coords, coords[1:])
    ]
    lengths = [math.hypot(*vector) for vector in vectors]
    pickup = sum(lengths[:2])
    end = sum(lengths)
    speed = SPEEDS[kind]
    revision, phase = divmod(elapsed, end / speed + 2 * STOP + 2)
    if phase < pickup / speed:
        distance, status = phase * speed, "TO_PICKUP"
    elif phase < pickup / speed + STOP:
        distance, status = pickup, "WAITING_PICKUP"
    elif phase < end / speed + STOP:
        distance, status = (phase - STOP) * speed, "TO_DROP"
    else:
        distance = end
        status = "WAITING_DROP" if phase < end / speed + 2 * STOP else "COMPLETED"
    left = distance
    for i, length in enumerate(lengths):
        if left <= length or i == len(lengths) - 1:
            t = min(1, left / length)
            a, b = coords[i:i + 2]
            lng, lat = (a[j] + (b[j] - a[j]) * t for j in range(2))
            heading = math.degrees(math.atan2(*vectors[i])) % 360
            return dict(lat=lat, lng=lng, heading=heading, status=status,
                        revision=int(revision), pickupDistance=pickup)
        left -= length


@app.websocket("/ws/vehicles")
async def vehicles(socket: WebSocket):
    origin = socket.headers.get("origin")
    if origin and origin not in {
        "http://localhost:5173", "http://127.0.0.1:5173",
        "http://localhost:4173", "http://127.0.0.1:4173",
    }:
        await socket.close(code=1008)
        return
    await socket.accept()
    revisions = {}
    try:
        while True:
            now = time.monotonic() - EPOCH
            batch = []
            for index, coords in enumerate(TRIPS):
                kind = tuple(SPEEDS)[index % len(SPEEDS)]
                record = track(coords, kind, now + index * 3)
                record.update(id=index + 1, type=kind)
                if revisions.get(index) != record["revision"]:
                    revisions[index] = record["revision"]
                    record["coords"] = coords
                batch.append(record)
            await socket.send_json(batch)
            try:
                if (await asyncio.wait_for(socket.receive(), INTERVAL))["type"] == "websocket.disconnect":
                    break
            except asyncio.TimeoutError:
                pass
    except (WebSocketDisconnect, OSError):
        pass
