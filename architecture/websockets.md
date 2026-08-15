# WebSocket Channels

Two real-time WebSocket endpoints. Both require a Clerk session JWT via query parameter.

---

## Authentication

WebSocket connections cannot send HTTP headers, so the JWT is passed as a query parameter:

```
ws://localhost:8000/tracking/ws?token=<clerk-session-jwt>
ws://localhost:8000/notifications/ws?token=<clerk-session-jwt>
```

On connection:
1. Server reads `websocket.query_params.get("token")`
2. Calls `decode_clerk_token(token)` — validates Clerk signature, issuer, and expiry
3. If missing or invalid → `websocket.close(code=4401, reason="...")` and returns
4. If valid → connection accepted, added to the broadcast pool

**Close codes:**
- `4401` — Missing or invalid token

---

## Channel 1: `/tracking/ws`

**Purpose:** Live vehicle positions and tracking events  
**Managed by:** `ConnectionManager` in `backend/routers/tracking.py`  
**Broadcasts from two sources:**

### Source A — Periodic snapshot (every 2 seconds)
Automatic broadcast from `broadcast_live_feed()` background loop:

```json
{
  "type": "tracking_snapshot",
  "vehicles": [
    {
      "id": 1,
      "license_plate": "SR-101",
      "status": "en_route",
      "lat": 25.2150,
      "lng": 55.2780,
      "assigned_route_id": "route-1-a3f9c2b1"
    }
  ],
  "events": [
    {
      "id": 42,
      "vehicle_id": 1,
      "ride_request_id": null,
      "route_plan_id": null,
      "event_type": "vehicle_location_update",
      "status": "en_route",
      "lat": 25.2150,
      "lng": 55.2780,
      "payload": { "speed_kmh": 45 },
      "created_at": "2026-08-07T10:30:00"
    }
  ]
}
```

### Source B — Immediate push on GPS update
Triggered by `POST /tracking/vehicles/{id}/location`:

```json
{
  "type": "vehicle_location_update",
  "vehicle": {
    "id": 1,
    "license_plate": "SR-101",
    "status": "en_route",
    "lat": 25.2150,
    "lng": 55.2780,
    "assigned_route_id": "route-1-a3f9c2b1"
  },
  "event": {
    "id": 43,
    "vehicle_id": 1,
    "event_type": "vehicle_location_update",
    "lat": 25.2150,
    "lng": 55.2780,
    "created_at": "2026-08-07T10:30:05"
  }
}
```

### Frontend usage
```javascript
const token = localStorage.getItem("access_token");
const ws = new WebSocket(`ws://localhost:8000/tracking/ws?token=${token}`);

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === "tracking_snapshot") {
    updateAllVehicleMarkers(data.vehicles);
  } else if (data.type === "vehicle_location_update") {
    updateSingleVehicleMarker(data.vehicle);
  }
};

ws.onclose = (event) => {
  if (event.code === 4401) {
    // Token expired — redirect to login
  }
};
```

---

## Channel 2: `/notifications/ws`

**Purpose:** Real-time notification delivery  
**Managed by:** `NotificationConnectionManager` in `backend/services/notifications.py`  
**Broadcasts from:** Every `create_notification()` call anywhere in the system

### Message format

```json
{
  "type": "notification",
  "notification": {
    "id": 88,
    "user_id": 3,
    "notification_type": "ride_status_updated",
    "title": "Ride status updated",
    "message": "Your ride request #12 changed from pending to assigned.",
    "related_entity_type": "ride_request",
    "related_entity_id": 12,
    "notification_metadata": {
      "old_status": "pending",
      "new_status": "assigned"
    },
    "is_read": false,
    "read_at": null,
    "created_at": "2026-08-07T10:30:00"
  }
}
```

### Important: broadcast goes to all clients
The notification broadcast is sent to **all connected WebSocket clients**, not just the intended recipient. The frontend must filter by `user_id`:

```javascript
const token = localStorage.getItem("access_token");
const currentUserId = getCurrentUserId(); // from decoded JWT
const ws = new WebSocket(`ws://localhost:8000/notifications/ws?token=${token}`);

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === "notification") {
    // Only show if it's for this user
    if (data.notification.user_id === currentUserId) {
      showNotificationToast(data.notification);
      incrementUnreadBadge();
    }
  }
};
```

### Notification types reference

| `notification_type` | When fired | Who receives |
|---|---|---|
| `ride_requested` | Passenger submits ride | Passenger |
| `ride_status_updated` | Ride status changes | Passenger (owner) |
| `ride_cancelled` | Ride cancelled | Passenger |
| `route_assigned` | Route optimized for their stop | All passengers on route |
| `route_optimized` | Route creation confirmed | Dispatcher (who triggered it) |
| `vehicle_tracking_update` | GPS update for their vehicle | All passengers on vehicle's route |
| `vehicle_location_logged` | GPS update confirmed | Driver who sent the update |

---

## Connection Manager — Dead Connection Cleanup

Both managers use the same pattern for handling dead connections gracefully:

```python
async def broadcast(self, message: str):
    dead = []
    for connection in self.active_connections:
        try:
            await connection.send_text(message)
        except Exception:
            dead.append(connection)  # mark dead
    for connection in dead:
        self.disconnect(connection)  # clean up after iteration
```

Dead connections (client closed browser, network drop, etc.) are silently removed. No error is raised.

---

## Reconnection

The server does not implement reconnection logic. The frontend should handle reconnects:

```javascript
function connectWebSocket(url) {
  const ws = new WebSocket(url);

  ws.onclose = (event) => {
    if (event.code !== 4401) {
      // Not an auth error — try to reconnect after 3 seconds
      setTimeout(() => connectWebSocket(url), 3000);
    }
  };

  return ws;
}
```

---

## Sending from Client

Both WebSocket connections are receive-only from the server's perspective. The server never reads client messages for any functional purpose — the `while True: await websocket.receive_text()` loop just keeps the connection alive and detects disconnects:

```python
try:
    while True:
        await websocket.receive_text()  # keeps connection alive
except WebSocketDisconnect:
    manager.disconnect(websocket)
```

The client does not need to send anything. All interaction happens through regular HTTP endpoints.
