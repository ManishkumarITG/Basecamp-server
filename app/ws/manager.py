"""In-process WebSocket hub, keyed by team.

Clients connected to a team receive broadcast events (a comment was added, a card
moved, etc.) so their UI updates live. State is in-memory, which is fine for a
single-process dev/uvicorn setup; a multi-worker deployment would back this with a
pub/sub (e.g. Redis) instead.
"""

import asyncio

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._rooms: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, team_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._rooms.setdefault(team_id, set()).add(websocket)

    async def disconnect(self, team_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            room = self._rooms.get(team_id)
            if room:
                room.discard(websocket)
                if not room:
                    self._rooms.pop(team_id, None)

    async def broadcast(self, team_id: str, message: dict) -> None:
        """Best-effort fan-out to everyone in the team's room."""
        for websocket in list(self._rooms.get(team_id, ())):
            try:
                await websocket.send_json(message)
            except Exception:  # noqa: BLE001 - drop sockets that error out
                await self.disconnect(team_id, websocket)


manager = ConnectionManager()
