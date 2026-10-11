"""Shared WebSocket plumbing: tolerant subprotocol acceptance and the dead-connection sweep, used by both the notification and tracking hubs."""

from typing import Awaitable, Callable, Iterable, List, Optional, Set

from fastapi import WebSocket


def offered_subprotocols(websocket: WebSocket) -> Set[str]:
    """The subprotocols the client offered, normalised to lower case."""
    return {
        part.strip().lower()
        for part in websocket.headers.get("sec-websocket-protocol", "").split(",")
        if part.strip()
    }


async def accept_connection(websocket: WebSocket, subprotocol: Optional[str] = None) -> None:
    """Echo subprotocol only when the client offered it; Starlette rejects otherwise, which broke Flutter clients."""
    if subprotocol and subprotocol.lower() in offered_subprotocols(websocket):
        await websocket.accept(subprotocol=subprotocol)
    else:
        await websocket.accept()


async def fan_out(entries: Iterable, send: Callable[[object], Awaitable[None]]) -> List:
    """Return entries whose send raised, so the caller drops dead connections without aborting the broadcast."""
    failed: List = []
    for entry in entries:
        try:
            await send(entry)
        except Exception:
            failed.append(entry)
    return failed
