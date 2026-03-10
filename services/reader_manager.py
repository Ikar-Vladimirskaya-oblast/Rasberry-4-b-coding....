from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from models.events import EventRecord, EventType
from models.readers import ReaderSnapshot, ReaderStatus
from services.readers.base import ReaderBase
from services.status_led import StatusLed
from services.websocket_manager import WebSocketManager
from storage.database import Database


LOGGER = logging.getLogger(__name__)


class ReaderManager:
    def __init__(
        self,
        readers: list[ReaderBase],
        database: Database,
        websocket_manager: WebSocketManager,
        status_leds: dict[str, StatusLed] | None = None,
    ) -> None:
        self._readers = {reader.id: reader for reader in readers}
        self._database = database
        self._websocket_manager = websocket_manager
        self._status_leds = status_leds or {}
        self._tasks: list[asyncio.Task[None]] = []
        self._stop_event = asyncio.Event()
        self._status_cache: dict[str, tuple[str, str | None]] = {}
        self._last_card_hits: dict[str, tuple[str, datetime]] = {}

    async def start(self) -> None:
        LOGGER.info("Starting reader manager for %s reader(s).", len(self._readers))
        system_event = await self._database.log_event(
            reader_id=None,
            event_type=EventType.SYSTEM_STARTED.value,
            message="Local RFID service started.",
        )
        await self._websocket_manager.broadcast({"type": "logs_updated", "event": system_event.to_payload()})

        for reader in self._readers.values():
            await self._initialize_status_led(reader.id)
            await reader.initialize()
            await self._sync_reader_state(reader, force=True)
            task = asyncio.create_task(self._poll_reader(reader), name=f"reader-poll-{reader.id}")
            self._tasks.append(task)

        await self.broadcast_status_update()

    async def stop(self) -> None:
        LOGGER.info("Stopping reader manager.")
        self._stop_event.set()
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        for reader in self._readers.values():
            await reader.close()
        for status_led in self._status_leds.values():
            await status_led.close()

    async def list_readers(self) -> list[dict[str, object]]:
        snapshots = [await reader.snapshot() for reader in self._readers.values()]
        return [snapshot.to_payload() for snapshot in snapshots]

    async def get_system_status(self) -> dict[str, object]:
        return {"system": "online", "readers": await self.list_readers()}

    async def get_logs(self, limit: int = 100) -> list[dict[str, object]]:
        logs = await self._database.fetch_logs(limit)
        return [event.to_payload() for event in logs]

    async def scan_reader(self, reader_id: str) -> dict[str, object]:
        reader = self._get_reader(reader_id)
        snapshot = await reader.snapshot()
        if snapshot.status in {ReaderStatus.DISCONNECTED, ReaderStatus.ERROR}:
            await reader.initialize()
            await self._sync_reader_state(reader)

        await reader.set_status(ReaderStatus.SCANNING, None)
        await self._apply_status_led(reader.id, ReaderStatus.SCANNING)
        await self.broadcast_status_update()

        uid = await reader.manual_scan()
        if await reader.health_check():
            await reader.set_status(ReaderStatus.CONNECTED, None)
        else:
            await reader.set_status(ReaderStatus.DISCONNECTED, "Reader is unavailable.")
        await self._sync_reader_state(reader)

        event_logged = False
        message = "No card detected."
        if uid:
            event_logged = await self._handle_card_detected(reader, uid, source="manual")
            mode = (await reader.snapshot()).mode
            if mode == "mock":
                message = f"Mock UID generated: {uid}"
            else:
                message = f"Card detected: {uid}"

        return {
            "ok": True,
            "message": message,
            "event_logged": event_logged,
            "reader": (await reader.snapshot()).to_payload(),
        }

    async def reset_reader(self, reader_id: str) -> dict[str, object]:
        reader = self._get_reader(reader_id)
        ok = await reader.reset()
        await self._sync_reader_state(reader, force=True)
        return {
            "ok": ok,
            "message": "Reader reset finished." if ok else "Reader reset attempted, device is still offline.",
            "event_logged": False,
            "reader": (await reader.snapshot()).to_payload(),
        }

    async def broadcast_status_update(self) -> None:
        payload = {"type": "status_update", "data": await self.get_system_status()}
        await self._websocket_manager.broadcast(payload)

    def _get_reader(self, reader_id: str) -> ReaderBase:
        reader = self._readers.get(reader_id)
        if reader is None:
            raise KeyError(reader_id)
        return reader

    async def _poll_reader(self, reader: ReaderBase) -> None:
        while not self._stop_event.is_set():
            try:
                snapshot = await reader.snapshot()
                if snapshot.status in {ReaderStatus.STARTING, ReaderStatus.DISCONNECTED, ReaderStatus.ERROR}:
                    await reader.initialize()
                    await self._sync_reader_state(reader)
                    await self._sleep_or_stop(reader.settings.reconnect_interval)
                    continue

                uid = await reader.read_uid()
                await self._sync_reader_state(reader)
                if uid:
                    await self._handle_card_detected(reader, uid, source="poll")
                await self._sleep_or_stop(reader.settings.poll_interval)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                LOGGER.exception("Unexpected poll loop error for %s", reader.id)
                await reader.set_status(ReaderStatus.ERROR, str(exc))
                await self._sync_reader_state(reader)
                await self._sleep_or_stop(reader.settings.reconnect_interval)

    async def _handle_card_detected(self, reader: ReaderBase, uid: str, source: str) -> bool:
        snapshot = await reader.snapshot()
        now = datetime.now(timezone.utc)
        last_hit = self._last_card_hits.get(reader.id)
        cooldown = reader.settings.scan_cooldown_seconds

        if last_hit is not None:
            last_uid, last_seen = last_hit
            if last_uid == uid and (now - last_seen).total_seconds() < cooldown:
                LOGGER.info("Duplicate card %s ignored for reader %s", uid, reader.id)
                await self.broadcast_status_update()
                return False

        self._last_card_hits[reader.id] = (uid, now)
        LOGGER.info("UID %s detected on reader %s via %s", uid, reader.id, source)

        event = await self._database.log_event(
            reader_id=reader.id,
            event_type=EventType.CARD_DETECTED.value,
            uid=uid,
            message=f"Card detected on {snapshot.name} via {source}.",
        )
        await self._flash_status_led(reader.id)
        await self._websocket_manager.broadcast(
            {
                "type": "card_detected",
                "reader_id": reader.id,
                "uid": uid,
                "timestamp": event.created_at.isoformat(),
                "reader": snapshot.to_payload(),
            }
        )
        await self._websocket_manager.broadcast({"type": "logs_updated", "event": event.to_payload()})
        await self.broadcast_status_update()
        return True

    async def _sync_reader_state(self, reader: ReaderBase, force: bool = False) -> None:
        snapshot = await reader.snapshot()
        previous_status, previous_error = self._status_cache.get(reader.id, (None, None))
        current_error = snapshot.last_error or None
        changed = force or previous_status != snapshot.status.value or previous_error != current_error
        self._status_cache[reader.id] = (snapshot.status.value, current_error)

        if not changed:
            return

        LOGGER.info(
            "Reader %s status=%s mode=%s error=%s",
            reader.id,
            snapshot.status.value,
            snapshot.mode,
            snapshot.last_error,
        )

        await self._apply_status_led(reader.id, snapshot.status)
        await self.broadcast_status_update()

        if snapshot.status == ReaderStatus.CONNECTED:
            if previous_status not in {ReaderStatus.CONNECTED.value, ReaderStatus.SCANNING.value}:
                event = await self._database.log_event(
                    reader_id=reader.id,
                    event_type=EventType.READER_INITIALIZED.value,
                    message=f"Reader {snapshot.name} initialized in {snapshot.mode} mode.",
                )
                await self._broadcast_reader_event("reader_connected", snapshot, event)
        elif snapshot.status == ReaderStatus.DISCONNECTED:
            if previous_status != ReaderStatus.DISCONNECTED.value:
                event = await self._database.log_event(
                    reader_id=reader.id,
                    event_type=EventType.READER_DISCONNECTED.value,
                    message=f"Reader {snapshot.name} is disconnected: {snapshot.last_error or 'unknown reason'}.",
                )
                await self._broadcast_reader_event("reader_disconnected", snapshot, event)
        elif snapshot.status == ReaderStatus.ERROR:
            if previous_status != ReaderStatus.ERROR.value or previous_error != current_error:
                event = await self._database.log_event(
                    reader_id=reader.id,
                    event_type=EventType.READER_ERROR.value,
                    message=f"Reader {snapshot.name} error: {snapshot.last_error or 'unknown error'}.",
                )
                await self._broadcast_reader_event("error", snapshot, event)

    async def _broadcast_reader_event(
        self,
        event_name: str,
        snapshot: ReaderSnapshot,
        event: EventRecord,
    ) -> None:
        await self._websocket_manager.broadcast(
            {
                "type": event_name,
                "timestamp": event.created_at.isoformat(),
                "message": event.message,
                "reader": snapshot.to_payload(),
            }
        )
        await self._websocket_manager.broadcast({"type": "logs_updated", "event": event.to_payload()})

    async def _sleep_or_stop(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            return

    async def _initialize_status_led(self, reader_id: str) -> None:
        status_led = self._status_leds.get(reader_id)
        if status_led is None:
            return
        await status_led.initialize()
        await status_led.apply_status(ReaderStatus.STARTING)

    async def _apply_status_led(self, reader_id: str, status: ReaderStatus) -> None:
        status_led = self._status_leds.get(reader_id)
        if status_led is None:
            return
        await status_led.apply_status(status)

    async def _flash_status_led(self, reader_id: str) -> None:
        status_led = self._status_leds.get(reader_id)
        if status_led is None:
            return
        await status_led.flash_card_detected()
