"""Team WebSocket endpoint for live updates.

Auth is via a ``token`` query param (browsers can't set headers on a WebSocket).
The socket is read-only from the client's side: the server only pushes events; any
inbound frames are ignored (and double as a keepalive / disconnect signal).
"""

from beanie import PydanticObjectId
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from app.core.security import decode_access_token
from app.models.team import Team
from app.services import auth_service
from app.ws.manager import manager

router = APIRouter()


@router.websocket("/ws/teams/{team_id}")
async def team_socket(websocket: WebSocket, team_id: str, token: str | None = Query(default=None)):
    payload = decode_access_token(token) if token else None
    user = await auth_service.get_user_by_id(payload["sub"]) if payload and payload.get("sub") else None
    if user is None or user.class_id is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        team = await Team.get(PydanticObjectId(team_id))
    except (ValueError, TypeError):
        team = None
    if team is None or team.class_id != user.class_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(team_id, websocket)
    try:
        while True:
            await websocket.receive_text()  # ignore inbound; keeps the socket open
    except WebSocketDisconnect:
        await manager.disconnect(team_id, websocket)
    except Exception:  # noqa: BLE001
        await manager.disconnect(team_id, websocket)
