from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from models.events import LogEventResponse
from models.readers import ActionResponse, ReaderResponse, SystemStatusResponse
from services.reader_manager import ReaderManager


router = APIRouter(prefix="/api", tags=["api"])


def get_reader_manager(request: Request) -> ReaderManager:
    return request.app.state.reader_manager


@router.get("/status", response_model=SystemStatusResponse)
async def get_status(request: Request) -> dict[str, object]:
    return await get_reader_manager(request).get_system_status()


@router.get("/readers", response_model=list[ReaderResponse])
async def list_readers(request: Request) -> list[dict[str, object]]:
    return await get_reader_manager(request).list_readers()


@router.get("/logs", response_model=list[LogEventResponse])
async def list_logs(request: Request) -> list[dict[str, object]]:
    return await get_reader_manager(request).get_logs()


@router.post("/readers/{reader_id}/scan", response_model=ActionResponse)
async def scan_reader(reader_id: str, request: Request) -> dict[str, object]:
    manager = get_reader_manager(request)
    try:
        return await manager.scan_reader(reader_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Reader {reader_id} not found.") from exc


@router.post("/readers/{reader_id}/reset", response_model=ActionResponse)
async def reset_reader(reader_id: str, request: Request) -> dict[str, object]:
    manager = get_reader_manager(request)
    try:
        return await manager.reset_reader(reader_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Reader {reader_id} not found.") from exc
