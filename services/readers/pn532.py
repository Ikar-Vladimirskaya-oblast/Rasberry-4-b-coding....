from __future__ import annotations

import asyncio
from typing import Any

from config import ReaderSettings
from models.readers import ReaderStatus
from services.readers.base import ReaderBase


class PN532Reader(ReaderBase):
    def __init__(self, settings: ReaderSettings) -> None:
        super().__init__(settings)
        self._device: Any | None = None
        self._resources: list[Any] = []
        self._mock_index = 0

    async def initialize(self) -> bool:
        if not self.settings.enabled:
            await self.set_status(ReaderStatus.DISCONNECTED, "Reader is disabled in config.")
            return False

        if self.settings.mock_mode:
            await self.set_mode("mock")
            await self.set_status(ReaderStatus.CONNECTED, None)
            return True

        await self.set_mode("hardware")
        try:
            device, resources = await asyncio.to_thread(self._create_device)
        except Exception as exc:
            self._device = None
            self._resources = []
            await self.set_status(ReaderStatus.DISCONNECTED, str(exc))
            return False

        self._device = device
        self._resources = resources
        await self.set_status(ReaderStatus.CONNECTED, None)
        return True

    async def read_uid(self, manual: bool = False) -> str | None:
        if not self.settings.enabled:
            return None

        if self.settings.mock_mode:
            if not manual:
                return None
            uid = self._next_mock_uid()
            await self.mark_card(uid)
            await self.set_status(ReaderStatus.CONNECTED, None)
            return uid

        if self._device is None:
            await self.set_status(ReaderStatus.DISCONNECTED, "Reader is not initialized.")
            return None

        try:
            uid = await asyncio.to_thread(self._read_once)
        except Exception as exc:
            self._device = None
            await self.set_status(ReaderStatus.DISCONNECTED, f"PN532 read failed: {exc}")
            return None

        if uid:
            await self.mark_card(uid)
            await self.set_status(ReaderStatus.CONNECTED, None)
        return uid

    async def health_check(self) -> bool:
        if self.settings.mock_mode:
            return True
        return self._device is not None

    async def close(self) -> None:
        await asyncio.to_thread(self._close_sync)
        self._device = None
        self._resources = []

    def _close_sync(self) -> None:
        for resource in self._resources:
            deinit = getattr(resource, "deinit", None)
            if callable(deinit):
                try:
                    deinit()
                except Exception:
                    continue

    def _next_mock_uid(self) -> str:
        if not self.settings.mock_uids:
            return "04AABBCCDD"
        uid = self.settings.mock_uids[self._mock_index % len(self.settings.mock_uids)]
        self._mock_index += 1
        return uid.upper()

    def _read_once(self) -> str | None:
        uid = self._device.read_passive_target(timeout=0.2)
        if uid is None:
            return None
        return "".join(f"{byte:02X}" for byte in uid)

    def _create_device(self) -> tuple[Any, list[Any]]:
        import board
        import busio
        from digitalio import DigitalInOut

        interface = self.settings.interface.lower()
        resources: list[Any] = []

        if interface == "i2c":
            from adafruit_pn532.i2c import PN532_I2C

            scl = self._resolve_pin(board, self.settings.scl_pin, "SCL")
            sda = self._resolve_pin(board, self.settings.sda_pin, "SDA")
            i2c = busio.I2C(scl, sda)
            resources.append(i2c)

            kwargs: dict[str, Any] = {"debug": False}
            reset_pin = self._optional_digital_pin(board, DigitalInOut, self.settings.reset_pin)
            req_pin = self._optional_digital_pin(board, DigitalInOut, self.settings.req_pin)
            if reset_pin is not None:
                kwargs["reset"] = reset_pin
                resources.append(reset_pin)
            if req_pin is not None:
                kwargs["req"] = req_pin
                resources.append(req_pin)
            if self.settings.i2c_address != 0x24:
                kwargs["address"] = self.settings.i2c_address

            pn532 = PN532_I2C(i2c, **kwargs)
        elif interface == "spi":
            from adafruit_pn532.spi import PN532_SPI

            sck = self._resolve_pin(board, self.settings.spi_clock_pin, "SCK")
            mosi = self._resolve_pin(board, self.settings.spi_mosi_pin, "MOSI")
            miso = self._resolve_pin(board, self.settings.spi_miso_pin, "MISO")
            spi = busio.SPI(sck, mosi, miso)
            resources.append(spi)

            cs_pin_name = self.settings.spi_cs_pin or "CE0"
            cs_pin = DigitalInOut(self._resolve_pin(board, cs_pin_name, cs_pin_name))
            resources.append(cs_pin)

            kwargs = {"debug": False}
            reset_pin = self._optional_digital_pin(board, DigitalInOut, self.settings.reset_pin)
            if reset_pin is not None:
                kwargs["reset"] = reset_pin
                resources.append(reset_pin)

            pn532 = PN532_SPI(spi, cs_pin, **kwargs)
        elif interface == "uart":
            from adafruit_pn532.uart import PN532_UART

            tx = self._resolve_pin(board, self.settings.uart_tx_pin, "TX")
            rx = self._resolve_pin(board, self.settings.uart_rx_pin, "RX")
            uart = busio.UART(tx, rx, baudrate=self.settings.uart_baudrate, timeout=0.2)
            resources.append(uart)

            kwargs = {"debug": False}
            reset_pin = self._optional_digital_pin(board, DigitalInOut, self.settings.reset_pin)
            if reset_pin is not None:
                kwargs["reset"] = reset_pin
                resources.append(reset_pin)

            pn532 = PN532_UART(uart, **kwargs)
        else:
            raise ValueError(f"Unsupported PN532 interface: {self.settings.interface}")

        _ic, ver, rev, _support = pn532.firmware_version
        if ver is None or rev is None:
            raise RuntimeError("Unable to read PN532 firmware version.")
        pn532.SAM_configuration()
        return pn532, resources

    @staticmethod
    def _resolve_pin(board_module: Any, configured_name: str | None, fallback_name: str) -> Any:
        pin_name = configured_name or fallback_name
        if not hasattr(board_module, pin_name):
            raise ValueError(f"Unknown board pin: {pin_name}")
        return getattr(board_module, pin_name)

    @staticmethod
    def _optional_digital_pin(board_module: Any, digital_in_out: Any, pin_name: str | None) -> Any | None:
        if pin_name is None:
            return None
        if not hasattr(board_module, pin_name):
            raise ValueError(f"Unknown board pin: {pin_name}")
        return digital_in_out(getattr(board_module, pin_name))
