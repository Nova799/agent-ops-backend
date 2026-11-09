import asyncio
import json
from typing import Set

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["websocket"])
_connections: Set[WebSocket] = set()


async def broadcast(event: dict):
    dead = []
    for ws in list(_connections):
        try:
            await ws.send_text(json.dumps(event))
        except Exception:  # noqa: BLE001
            dead.append(ws)
    for ws in dead:
        _connections.discard(ws)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    _connections.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        _connections.discard(websocket)
    except Exception:  # noqa: BLE001
        _connections.discard(websocket)