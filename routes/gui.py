from __future__ import annotations

import logging

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from services.reader_manager import ReaderManager
from services.websocket_manager import WebSocketManager


LOGGER = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return request.app.state.templates.TemplateResponse(
        "index.html",
        {"request": request, "page_title": "RFID Reader Test Stand"},
    )


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    websocket_manager: WebSocketManager = websocket.app.state.websocket_manager
    reader_manager: ReaderManager = websocket.app.state.reader_manager

    await websocket_manager.connect(websocket)
    await websocket.send_json({"type": "status_update", "data": await reader_manager.get_system_status()})
    await websocket.send_json({"type": "logs_updated", "logs": await reader_manager.get_logs()})

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await websocket_manager.disconnect(websocket)
    except Exception:
        LOGGER.exception("WebSocket error")
        await websocket_manager.disconnect(websocket)
