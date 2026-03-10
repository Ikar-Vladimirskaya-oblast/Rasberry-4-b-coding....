from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class ReaderStatus(str, Enum):
    STARTING = "starting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    SCANNING = "scanning"


@dataclass
class ReaderSnapshot:
    id: str
    name: str
    type: str
    interface: str
    status: ReaderStatus
    mode: str
    enabled: bool
    last_uid: str | None = None
    last_seen: datetime | None = None
    last_error: str | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "interface": self.interface,
            "status": self.status.value,
            "mode": self.mode,
            "enabled": self.enabled,
            "last_uid": self.last_uid,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "last_error": self.last_error,
        }


class ReaderResponse(BaseModel):
    id: str
    name: str
    type: str
    interface: str
    status: str
    mode: str
    enabled: bool
    last_uid: str | None = None
    last_seen: datetime | None = None
    last_error: str | None = None


class SystemStatusResponse(BaseModel):
    system: str
    readers: list[ReaderResponse]


class ActionResponse(BaseModel):
    ok: bool
    message: str
    event_logged: bool = False
    reader: ReaderResponse | None = None
