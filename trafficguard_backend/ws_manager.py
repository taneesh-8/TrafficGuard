"""
ws_manager.py

Simple in-memory WebSocket connection manager.
Dead connections are silently dropped on send failure.
"""
from __future__ import annotations
import json
import logging
from typing import Any

from fastapi import WebSocket

log = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self._active: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._active.add(ws)
        log.info("WS client connected. Active connections: %d", len(self._active))

    def disconnect(self, ws: WebSocket) -> None:
        self._active.discard(ws)
        log.info("WS client disconnected. Active connections: %d", len(self._active))

    async def broadcast(self, data: dict[str, Any]) -> None:
        """Broadcast JSON to all connected clients; drop dead connections."""
        dead: set[WebSocket] = set()
        message = json.dumps(data, default=str)
        for ws in list(self._active):
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self._active.discard(ws)
        if dead:
            log.info("Dropped %d dead WS connection(s)", len(dead))


manager = ConnectionManager()
