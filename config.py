from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


LOGGER = logging.getLogger(__name__)


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: Any, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        base = 16 if value.strip().lower().startswith("0x") else 10
        return int(value, base)
    return int(value)


def _as_float(value: Any, default: float) -> float:
    if value is None:
        return default
    return float(value)


def _as_str_list(value: Any, default: list[str]) -> list[str]:
    if value is None:
        return list(default)
    if isinstance(value, list):
        return [str(item).strip().upper() for item in value if str(item).strip()]
    return list(default)


@dataclass
class ReaderSettings:
    id: str
    name: str
    type: str = "pn532"
    interface: str = "i2c"
    enabled: bool = True
    mock_mode: bool = False
    poll_interval: float = 0.5
    scan_cooldown_seconds: float = 2.0
    reconnect_interval: float = 5.0
    i2c_address: int = 0x24
    scl_pin: str | None = None
    sda_pin: str | None = None
    spi_clock_pin: str | None = None
    spi_mosi_pin: str | None = None
    spi_miso_pin: str | None = None
    spi_cs_pin: str | None = None
    uart_tx_pin: str | None = None
    uart_rx_pin: str | None = None
    uart_baudrate: int = 115200
    reset_pin: str | None = None
    req_pin: str | None = None
    mock_uids: list[str] = field(default_factory=lambda: ["04AABBCCDD"])

    @classmethod
    def from_dict(cls, data: dict[str, Any], force_mock: bool = False) -> "ReaderSettings":
        return cls(
            id=str(data["id"]),
            name=str(data.get("name", data["id"])),
            type=str(data.get("type", "pn532")).lower(),
            interface=str(data.get("interface", "i2c")).lower(),
            enabled=bool(data.get("enabled", True)),
            mock_mode=force_mock or bool(data.get("mock_mode", False)),
            poll_interval=_as_float(data.get("poll_interval"), 0.5),
            scan_cooldown_seconds=_as_float(data.get("scan_cooldown_seconds"), 2.0),
            reconnect_interval=_as_float(data.get("reconnect_interval"), 5.0),
            i2c_address=_as_int(data.get("i2c_address"), 0x24),
            scl_pin=data.get("scl_pin"),
            sda_pin=data.get("sda_pin"),
            spi_clock_pin=data.get("spi_clock_pin"),
            spi_mosi_pin=data.get("spi_mosi_pin"),
            spi_miso_pin=data.get("spi_miso_pin"),
            spi_cs_pin=data.get("spi_cs_pin"),
            uart_tx_pin=data.get("uart_tx_pin"),
            uart_rx_pin=data.get("uart_rx_pin"),
            uart_baudrate=_as_int(data.get("uart_baudrate"), 115200),
            reset_pin=data.get("reset_pin"),
            req_pin=data.get("req_pin"),
            mock_uids=_as_str_list(data.get("mock_uids"), ["04AABBCCDD"]),
        )


@dataclass
class AppSettings:
    project_root: Path
    host: str
    port: int
    log_level: str
    database_path: Path
    readers_config_path: Path
    readers: list[ReaderSettings]


DEFAULT_READER_CONFIG = [
    {
        "id": "reader_1",
        "name": "Test Reader 1",
        "type": "pn532",
        "interface": "i2c",
        "enabled": True,
        "mock_mode": True,
        "poll_interval": 0.5,
        "scan_cooldown_seconds": 2.0,
        "reconnect_interval": 5.0,
        "i2c_address": "0x24",
        "mock_uids": ["04AABBCCDD", "04FFEE1122"],
    }
]


def _load_readers_config(config_path: Path, force_mock: bool) -> list[ReaderSettings]:
    if not config_path.exists():
        LOGGER.warning("Reader config %s is missing, using built-in mock config.", config_path)
        data = DEFAULT_READER_CONFIG
    else:
        with config_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)

    readers = [ReaderSettings.from_dict(entry, force_mock=force_mock) for entry in data]
    if not readers:
        LOGGER.warning("Reader config is empty, falling back to built-in mock config.")
        readers = [ReaderSettings.from_dict(entry, force_mock=force_mock) for entry in DEFAULT_READER_CONFIG]
    return readers


def load_settings(project_root: Path | None = None) -> AppSettings:
    root = project_root or Path(__file__).resolve().parent
    host = os.getenv("APP_HOST", "0.0.0.0")
    port = _as_int(os.getenv("APP_PORT"), 8000)
    log_level = os.getenv("APP_LOG_LEVEL", "INFO").upper()
    readers_config_path = root / os.getenv("READERS_CONFIG_PATH", "readers.json")
    database_path = root / os.getenv("DATABASE_PATH", "storage/events.db")
    force_mock = _as_bool(os.getenv("APP_MOCK_ALL_READERS"), default=False)

    readers = _load_readers_config(readers_config_path, force_mock=force_mock)
    return AppSettings(
        project_root=root,
        host=host,
        port=port,
        log_level=log_level,
        database_path=database_path,
        readers_config_path=readers_config_path,
        readers=readers,
    )
