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
    i2c_address: int
    i2c_mux_address: int | None
    i2c_mux_channel: int | None
    status: ReaderStatus
    mode: str
    enabled: bool
    led_enabled: bool
    led_mode: str
    led_gpio_pin: int | None
    led_active_high: bool
    led_pixel_count: int
    led_pixel_index: int
    led_brightness: int
    last_uid: str | None = None
    last_seen: datetime | None = None
    last_error: str | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "interface": self.interface,
            "i2c_address": self.i2c_address,
            "i2c_mux_address": self.i2c_mux_address,
            "i2c_mux_channel": self.i2c_mux_channel,
            "status": self.status.value,
            "mode": self.mode,
            "enabled": self.enabled,
            "led_enabled": self.led_enabled,
            "led_mode": self.led_mode,
            "led_gpio_pin": self.led_gpio_pin,
            "led_active_high": self.led_active_high,
            "led_pixel_count": self.led_pixel_count,
            "led_pixel_index": self.led_pixel_index,
            "led_brightness": self.led_brightness,
            "last_uid": self.last_uid,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "last_error": self.last_error,
        }


class ReaderResponse(BaseModel):
    id: str
    name: str
    type: str
    interface: str
    i2c_address: int
    i2c_mux_address: int | None = None
    i2c_mux_channel: int | None = None
    status: str
    mode: str
    enabled: bool
    led_enabled: bool
    led_mode: str
    led_gpio_pin: int | None = None
    led_active_high: bool
    led_pixel_count: int
    led_pixel_index: int
    led_brightness: int
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
