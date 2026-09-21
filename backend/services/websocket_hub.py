"""Shared WebSocket plumbing.

Two hubs fan out to connected clients — the notification hub (keyed per user)
and the tracking hub (keyed per role) — and both had grown their own copy of
the same two primitives: tolerant subprotocol acceptance and the dead-connection
sweep. They live here once; only the scoping differs, and that stays with each
hub.
"""

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
    """Accept the socket, echoing ``subprotocol`` only if the client offered it.

    Starlette rejects a subprotocol the client never offered, which is how
    Flutter clients (which offer none) used to fail to connect.
    """
    if subprotocol and subprotocol.lower() in offered_subprotocols(websocket):
        await websocket.accept(subprotocol=subprotocol)
    else:
        await websocket.accept()


async def fan_out(entries: Iterable, send: Callable[[object], Awaitable[None]]) -> List:
    """Await ``send`` for each entry, returning the ones that raised.

    A failed send means the connection is dead; the caller drops exactly those
    instead of aborting the whole broadcast. ``send`` may return without sending
    to skip an entry (e.g. a client that may not see this payload).
    """
    failed: List = []
    for entry in entries:
        try:
            await send(entry)
        except Exception:
            failed.append(entry)
    return failed
