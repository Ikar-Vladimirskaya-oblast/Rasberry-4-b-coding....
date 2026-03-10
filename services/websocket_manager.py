from __future__ import annotations

import asyncio
import logging

from fastapi import WebSocket


LOGGER = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)
        LOGGER.info("WebSocket connected from %s", websocket.client)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)
        LOGGER.info("WebSocket disconnected from %s", websocket.client)

    async def broadcast(self, payload: dict[str, object]) -> None:
        async with self._lock:
            connections = list(self._connections)
        stale_connections: list[WebSocket] = []
        for connection in connections:
            try:
                await connection.send_json(payload)
            except Exception:
                stale_connections.append(connection)
        for connection in stale_connections:
            await self.disconnect(connection)
