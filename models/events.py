from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class EventType(str, Enum):
    SYSTEM_STARTED = "system_started"
    READER_INITIALIZED = "reader_initialized"
    CARD_DETECTED = "card_detected"
    READER_ERROR = "reader_error"
    READER_DISCONNECTED = "reader_disconnected"


@dataclass
class EventRecord:
    id: int | None
    reader_id: str | None
    event_type: str
    uid: str | None
    message: str
    created_at: datetime

    def to_payload(self) -> dict[str, object]:
        return {
            "id": self.id,
            "reader_id": self.reader_id,
            "event_type": self.event_type,
            "uid": self.uid,
            "message": self.message,
            "created_at": self.created_at.isoformat(),
        }


class LogEventResponse(BaseModel):
    id: int | None
    reader_id: str | None
    event_type: str
    uid: str | None
    message: str
    created_at: datetime
