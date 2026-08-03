"""WebSocket connection manager for real-time task updates."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog
from fastapi import WebSocket, WebSocketDisconnect

logger = structlog.get_logger(__name__)


class ConnectionManager:
    """Manages WebSocket connections and broadcasts messages to clients."""

    def __init__(self) -> None:
        self._active: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, client_id: str) -> None:
        """Accept and register a WebSocket connection."""
        await websocket.accept()
        self._active[client_id] = websocket
        logger.info("ws.connected", client_id=client_id, total=len(self._active))

    def disconnect(self, client_id: str) -> None:
        """Remove a connection from the active pool."""
        self._active.pop(client_id, None)
        logger.info("ws.disconnected", client_id=client_id, total=len(self._active))

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Send a JSON message to all connected clients."""
        payload = json.dumps(message)
        disconnected: list[str] = []

        for client_id, ws in self._active.items():
            try:
                await ws.send_text(payload)
            except Exception:
                disconnected.append(client_id)

        for client_id in disconnected:
            self.disconnect(client_id)

    async def send_to(self, client_id: str, message: dict[str, Any]) -> None:
        """Send a JSON message to a specific client."""
        ws = self._active.get(client_id)
        if ws is None:
            logger.warning("ws.send_to_unknown_client", client_id=client_id)
            return
        try:
            await ws.send_text(json.dumps(message))
        except Exception:
            self.disconnect(client_id)


# Module-level singleton
manager = ConnectionManager()


async def websocket_endpoint(websocket: WebSocket) -> None:
    """Handle the ``/ws/tasks`` WebSocket endpoint.

    Supports a simple ping/pong keepalive protocol:
    - Client sends ``{"type": "ping"}`` and receives ``{"type": "pong"}``.
    - Server sends periodic pings if no data is received for 120s.
    """
    client_id = websocket.query_params.get("client_id", str(id(websocket)))

    await manager.connect(websocket, client_id)

    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=120)
            except asyncio.TimeoutError:
                # Send a server-initiated ping to keep the connection alive
                try:
                    await websocket.send_text(json.dumps({"type": "ping"}))
                except Exception:
                    break
                continue

            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_text(
                    json.dumps({"type": "error", "detail": "Invalid JSON"})
                )
                continue

            msg_type = message.get("type", "")

            if msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
            elif msg_type == "pong":
                # Client responded to our ping -- connection is alive
                pass
            else:
                logger.debug("ws.unhandled_message", client_id=client_id, type=msg_type)

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error("ws.error", client_id=client_id, error=str(exc))
    finally:
        manager.disconnect(client_id)
