from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from config import ReaderSettings
from models.readers import ReaderStatus


LOGGER = logging.getLogger(__name__)


class StatusLed:
    def __init__(self, settings: ReaderSettings) -> None:
        self._reader_id = settings.id
        self._enabled = settings.led_enabled
        self._gpio_pin = settings.led_gpio_pin
        self._active_high = settings.led_active_high
        self._led = None
        self._available = False
        self._current_status = ReaderStatus.DISCONNECTED
        self._pattern_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    async def initialize(self) -> bool:
        if not self._enabled or self._gpio_pin is None:
            return False

        try:
            from gpiozero import LED

            self._led = LED(self._gpio_pin, active_high=self._active_high, initial_value=False)
            self._available = True
            LOGGER.info("Status LED ready for %s on GPIO %s", self._reader_id, self._gpio_pin)
            return True
        except Exception as exc:
            self._available = False
            self._led = None
            LOGGER.warning("Status LED init failed for %s: %s", self._reader_id, exc)
            return False

    async def apply_status(self, status: ReaderStatus) -> None:
        self._current_status = status
        if not self._available or self._led is None:
            return

        pattern = self._pattern_for_status(status)
        async with self._lock:
            await self._cancel_pattern_locked()
            if pattern == "on":
                self._led.on()
            elif pattern == "off":
                self._led.off()
            elif pattern == "blink-slow":
                self._pattern_task = asyncio.create_task(self._blink_loop(0.45, 0.45))
            elif pattern == "blink-fast":
                self._pattern_task = asyncio.create_task(self._blink_loop(0.12, 0.12))
            elif pattern == "blink-error":
                self._pattern_task = asyncio.create_task(self._error_blink_loop())

    async def flash_card_detected(self) -> None:
        if not self._available or self._led is None:
            return

        async with self._lock:
            await self._cancel_pattern_locked()
            for _ in range(2):
                self._led.on()
                await asyncio.sleep(0.08)
                self._led.off()
                await asyncio.sleep(0.08)

        await self.apply_status(self._current_status)

    async def close(self) -> None:
        async with self._lock:
            await self._cancel_pattern_locked()
            if self._led is not None:
                self._led.off()
                self._led.close()
                self._led = None
            self._available = False

    async def _cancel_pattern_locked(self) -> None:
        if self._pattern_task is None:
            return
        self._pattern_task.cancel()
        with suppress(asyncio.CancelledError):
            await self._pattern_task
        self._pattern_task = None

    async def _blink_loop(self, on_seconds: float, off_seconds: float) -> None:
        while True:
            self._led.on()
            await asyncio.sleep(on_seconds)
            self._led.off()
            await asyncio.sleep(off_seconds)

    async def _error_blink_loop(self) -> None:
        while True:
            self._led.on()
            await asyncio.sleep(0.08)
            self._led.off()
            await asyncio.sleep(0.12)
            self._led.on()
            await asyncio.sleep(0.08)
            self._led.off()
            await asyncio.sleep(0.7)

    @staticmethod
    def _pattern_for_status(status: ReaderStatus) -> str:
        if status == ReaderStatus.CONNECTED:
            return "on"
        if status == ReaderStatus.DISCONNECTED:
            return "off"
        if status == ReaderStatus.STARTING:
            return "blink-slow"
        if status == ReaderStatus.SCANNING:
            return "blink-fast"
        return "blink-error"


__all__ = ["StatusLed"]
