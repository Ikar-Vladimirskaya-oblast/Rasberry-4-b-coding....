from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from config import ReaderSettings
from models.readers import ReaderSnapshot, ReaderStatus


class ReaderBase(ABC):
    def __init__(self, settings: ReaderSettings) -> None:
        self.settings = settings
        self._status = ReaderStatus.STARTING if settings.enabled else ReaderStatus.DISCONNECTED
        self._last_uid: str | None = None
        self._last_seen: datetime | None = None
        self._last_error: str | None = None
        self._state_lock = asyncio.Lock()
        self._mode = "mock" if settings.mock_mode else "hardware"

    @property
    def id(self) -> str:
        return self.settings.id

    @property
    def name(self) -> str:
        return self.settings.name

    async def snapshot(self) -> ReaderSnapshot:
        async with self._state_lock:
            return ReaderSnapshot(
                id=self.settings.id,
                name=self.settings.name,
                type=self.settings.type,
                interface=self.settings.interface,
                status=self._status,
                mode=self._mode,
                enabled=self.settings.enabled,
                last_uid=self._last_uid,
                last_seen=self._last_seen,
                last_error=self._last_error,
            )

    async def set_status(self, status: ReaderStatus, last_error: str | None = None) -> None:
        async with self._state_lock:
            self._status = status
            self._last_error = last_error

    async def set_mode(self, mode: str) -> None:
        async with self._state_lock:
            self._mode = mode

    async def mark_card(self, uid: str, seen_at: datetime | None = None) -> None:
        async with self._state_lock:
            self._last_uid = uid
            self._last_seen = seen_at or datetime.now(timezone.utc)
            self._last_error = None

    async def manual_scan(self) -> str | None:
        return await self.read_uid(manual=True)

    async def reset(self) -> bool:
        await self.close()
        await self.set_status(ReaderStatus.STARTING, None)
        return await self.initialize()

    @abstractmethod
    async def initialize(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def read_uid(self, manual: bool = False) -> str | None:
        raise NotImplementedError

    @abstractmethod
    async def health_check(self) -> bool:
        raise NotImplementedError

    async def close(self) -> None:
        return None
