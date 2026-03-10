from __future__ import annotations

import asyncio
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from models.events import EventRecord


class Database:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._connection: sqlite3.Connection | None = None
        self._lock = threading.Lock()

    async def initialize(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(self._initialize_sync)

    def _initialize_sync(self) -> None:
        self._connection = sqlite3.connect(self._path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        with self._lock:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reader_id TEXT,
                    event_type TEXT NOT NULL,
                    uid TEXT,
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            self._connection.commit()

    async def close(self) -> None:
        if self._connection is not None:
            await asyncio.to_thread(self._connection.close)
            self._connection = None

    async def log_event(
        self,
        reader_id: str | None,
        event_type: str,
        message: str,
        uid: str | None = None,
    ) -> EventRecord:
        created_at = datetime.now(timezone.utc)
        return await asyncio.to_thread(
            self._log_event_sync,
            reader_id,
            event_type,
            uid,
            message,
            created_at,
        )

    def _log_event_sync(
        self,
        reader_id: str | None,
        event_type: str,
        uid: str | None,
        message: str,
        created_at: datetime,
    ) -> EventRecord:
        if self._connection is None:
            raise RuntimeError("Database is not initialized.")
        with self._lock:
            cursor = self._connection.execute(
                """
                INSERT INTO events (reader_id, event_type, uid, message, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (reader_id, event_type, uid, message, created_at.isoformat()),
            )
            self._connection.commit()
            event_id = int(cursor.lastrowid)
        return EventRecord(
            id=event_id,
            reader_id=reader_id,
            event_type=event_type,
            uid=uid,
            message=message,
            created_at=created_at,
        )

    async def fetch_logs(self, limit: int = 100) -> list[EventRecord]:
        return await asyncio.to_thread(self._fetch_logs_sync, limit)

    def _fetch_logs_sync(self, limit: int) -> list[EventRecord]:
        if self._connection is None:
            raise RuntimeError("Database is not initialized.")
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT id, reader_id, event_type, uid, message, created_at
                FROM events
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            EventRecord(
                id=int(row["id"]),
                reader_id=row["reader_id"],
                event_type=row["event_type"],
                uid=row["uid"],
                message=row["message"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]
