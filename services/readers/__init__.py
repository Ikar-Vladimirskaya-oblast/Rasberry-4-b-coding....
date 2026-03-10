from config import ReaderSettings
from services.readers.base import ReaderBase
from services.readers.pn532 import PN532Reader


def build_reader(settings: ReaderSettings) -> ReaderBase:
    if settings.type == "pn532":
        return PN532Reader(settings)
    raise ValueError(f"Unsupported reader type: {settings.type}")


__all__ = ["PN532Reader", "ReaderBase", "build_reader"]
