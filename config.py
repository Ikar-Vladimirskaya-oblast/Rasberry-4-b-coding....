from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "organizer.sqlite3"

TCA_ADDR = 0x70
PN532_ADDR = 0x24
I2C_BUS_NO = 1

LED_COUNT = 4
LED_PIN = 18
LED_FREQ_HZ = 800000
LED_DMA = 10
LED_INVERT = False
LED_CHANNEL = 0

# App slots are mapped to the reversed physical tray positions.
SLOTS = [
    {"slot_number": 1, "tca_channel": 3, "led_number": 4, "name": "Слот 1"},
    {"slot_number": 2, "tca_channel": 4, "led_number": 3, "name": "Слот 2"},
    {"slot_number": 3, "tca_channel": 5, "led_number": 2, "name": "Слот 3"},
    {"slot_number": 4, "tca_channel": 6, "led_number": 1, "name": "Слот 4"},
]

DEFAULT_SETTINGS = {
    "brightness": "80",
    "led_enabled": "0",
    "switch_delay": "0.08",
    "read_delay": "0.05",
    "read_timeout": "0.18",
    "loop_delay": "0.04",
    "reinit_delay": "1.0",
    "cloud_enabled": "1",
    "cloud_device_id": "raspberry-organizer",
    "cloud_url": "ws://141.105.68.221:8091/ws/raspberry-organizer",
    "cloud_sync_interval": "8",
}
