from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import ClassVar

from config import ReaderSettings
from models.readers import ReaderStatus


LOGGER = logging.getLogger(__name__)


class _AddressableStrip:
    def __init__(self, gpio_pin: int, pixel_count: int, brightness: int) -> None:
        from rpi_ws281x import PixelStrip

        self.gpio_pin = gpio_pin
        self.pixel_count = pixel_count
        self.brightness = brightness
        self._lock = asyncio.Lock()
        self._strip = PixelStrip(
            pixel_count,
            gpio_pin,
            freq_hz=800_000,
            dma=10,
            invert=False,
            brightness=brightness,
            channel=0,
        )
        self._strip.begin()

    async def set_pixel(self, pixel_index: int, color: tuple[int, int, int]) -> None:
        from rpi_ws281x import Color

        red, green, blue = color
        async with self._lock:
            self._strip.setPixelColor(pixel_index, Color(red, green, blue))
            self._strip.show()


class StatusLed:
    _addressable_registry: ClassVar[dict[tuple[int, int, int], _AddressableStrip]] = {}

    def __init__(self, settings: ReaderSettings) -> None:
        self._reader_id = settings.id
        self._enabled = settings.led_enabled
        self._mode = settings.led_mode
        self._gpio_pin = settings.led_gpio_pin
        self._active_high = settings.led_active_high
        self._pixel_count = settings.led_pixel_count
        self._pixel_index = settings.led_pixel_index
        self._brightness = settings.led_brightness
        self._led = None
        self._addressable_strip: _AddressableStrip | None = None
        self._available = False
        self._current_status = ReaderStatus.DISCONNECTED
        self._pattern_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    async def initialize(self) -> bool:
        if not self._enabled or self._gpio_pin is None:
            return False

        try:
            if self._mode == "addressable":
                if self._pixel_count <= 0:
                    raise ValueError("led_pixel_count must be greater than zero.")
                if not 0 <= self._pixel_index < self._pixel_count:
                    raise ValueError("led_pixel_index must fit inside led_pixel_count.")
                self._addressable_strip = self._get_or_create_addressable_strip()
                LOGGER.info(
                    "Addressable status LED ready for %s on GPIO %s pixel %s/%s",
                    self._reader_id,
                    self._gpio_pin,
                    self._pixel_index,
                    self._pixel_count,
                )
            else:
                from gpiozero import LED

                self._led = LED(self._gpio_pin, active_high=self._active_high, initial_value=False)
                LOGGER.info("GPIO status LED ready for %s on GPIO %s", self._reader_id, self._gpio_pin)
            self._available = True
            return True
        except Exception as exc:
            self._available = False
            self._led = None
            self._addressable_strip = None
            LOGGER.warning("Status LED init failed for %s: %s", self._reader_id, exc)
            return False

    async def apply_status(self, status: ReaderStatus) -> None:
        self._current_status = status
        if not self._available:
            return

        pattern = self._pattern_for_status(status)
        async with self._lock:
            await self._cancel_pattern_locked()
            if pattern == "on":
                await self._set_color(self._color_for_status(status))
            elif pattern == "off":
                await self._set_off()
            elif pattern == "blink-slow":
                self._pattern_task = asyncio.create_task(self._blink_loop(0.45, 0.45))
            elif pattern == "blink-fast":
                self._pattern_task = asyncio.create_task(self._blink_loop(0.12, 0.12))
            elif pattern == "blink-error":
                self._pattern_task = asyncio.create_task(self._error_blink_loop())

    async def flash_card_detected(self) -> None:
        if not self._available:
            return

        async with self._lock:
            await self._cancel_pattern_locked()
            for _ in range(2):
                await self._set_color((160, 160, 160))
                await asyncio.sleep(0.08)
                await self._set_off()
                await asyncio.sleep(0.08)

        await self.apply_status(self._current_status)

    async def close(self) -> None:
        async with self._lock:
            await self._cancel_pattern_locked()
            if self._led is not None:
                self._led.off()
                self._led.close()
                self._led = None
            if self._addressable_strip is not None:
                await self._set_off()
                self._addressable_strip = None
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
            await self._set_color(self._color_for_status(self._current_status))
            await asyncio.sleep(on_seconds)
            await self._set_off()
            await asyncio.sleep(off_seconds)

    async def _error_blink_loop(self) -> None:
        while True:
            await self._set_color((160, 0, 0))
            await asyncio.sleep(0.08)
            await self._set_off()
            await asyncio.sleep(0.12)
            await self._set_color((160, 0, 0))
            await asyncio.sleep(0.08)
            await self._set_off()
            await asyncio.sleep(0.7)

    async def _set_color(self, color: tuple[int, int, int]) -> None:
        if self._mode == "addressable":
            if self._addressable_strip is not None:
                await self._addressable_strip.set_pixel(self._pixel_index, color)
            return
        if self._led is None:
            return
        if color == (0, 0, 0):
            self._led.off()
        else:
            self._led.on()

    async def _set_off(self) -> None:
        await self._set_color((0, 0, 0))

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

    @staticmethod
    def _color_for_status(status: ReaderStatus) -> tuple[int, int, int]:
        if status == ReaderStatus.CONNECTED:
            return (0, 110, 0)
        if status == ReaderStatus.STARTING:
            return (0, 0, 120)
        if status == ReaderStatus.SCANNING:
            return (140, 80, 0)
        if status == ReaderStatus.ERROR:
            return (160, 0, 0)
        return (0, 0, 0)

    def _get_or_create_addressable_strip(self) -> _AddressableStrip:
        key = (self._gpio_pin, self._pixel_count, self._brightness)
        strip = self._addressable_registry.get(key)
        if strip is None:
            strip = _AddressableStrip(
                gpio_pin=self._gpio_pin,
                pixel_count=self._pixel_count,
                brightness=self._brightness,
            )
            self._addressable_registry[key] = strip
        return strip


__all__ = ["StatusLed"]
