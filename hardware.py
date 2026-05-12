import threading
import time
import traceback

import db
from config import (
    I2C_BUS_NO,
    LED_CHANNEL,
    LED_COUNT,
    LED_DMA,
    LED_FREQ_HZ,
    LED_INVERT,
    LED_PIN,
    PN532_ADDR,
    TCA_ADDR,
)


STATUS_LABELS = {
    "empty": "Пусто",
    "ok": "На месте",
    "unknown": "Неизвестная метка",
    "wrong": "Чужой слот",
    "error": "Ошибка ридера",
}


EMPTY_CONFIRM_READS = 3


class HardwareController:
    def __init__(self):
        self.stop_event = threading.Event()
        self.recheck_event = threading.Event()
        self.lock = threading.Lock()
        self.thread = None
        self.runtime = {
            "running": False,
            "hardware_ready": False,
            "last_tick": None,
            "last_uid": None,
            "last_uid_slot": None,
            "message": "Ожидание запуска",
            "readers": {},
        }
        self.strip = None
        self.selector = None
        self.i2c = None
        self.readers = {}
        self.last_signatures = {}
        self.last_init_attempt = {}
        self.slot_read_cache = {}
        self.current_brightness = None
        self.highlight = {"until": 0, "leds": {}, "message": None}
        self.highlight_was_active = False
        self.last_tick_monotonic = None

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._loop, name="hardware-loop", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=3)
        self._safe_all_off()
        self._safe_disable_tca()

    def snapshot(self):
        with self.lock:
            data = dict(self.runtime)
            data["readers"] = {key: dict(value) for key, value in self.runtime["readers"].items()}
            data["healthy"] = self.is_healthy()
            return data

    def is_healthy(self):
        thread_alive = bool(self.thread and self.thread.is_alive())
        runtime = self.runtime
        if not thread_alive or not runtime.get("running") or not runtime.get("hardware_ready"):
            return False
        if self.last_tick_monotonic is None:
            return True
        return time.monotonic() - self.last_tick_monotonic < 30

    def request_recheck(self):
        self.recheck_event.set()
        with self.lock:
            self.runtime["message"] = "Переинициализация ридеров"

    def set_led_enabled(self, enabled):
        db.set_setting("led_enabled", "0")
        self._clear_highlight()
        self._safe_all_off()
        message = (
            "Статусная LED-подсветка отключена. Используйте подсветку свободных ячеек или поиск предмета."
            if enabled
            else "LED выключены"
        )
        self._set_runtime(message=message)

    def highlight_empty_unbound(self, duration=10):
        slots = db.list_slots()
        leds = {}
        for slot in slots:
            is_unbound = slot.get("expected_item_id") is None
            is_empty = not slot.get("current_uid")
            if is_unbound and is_empty:
                leds[slot["led_number"]] = "blue"
        self._set_highlight(leds, duration, "Подсветка свободных ячеек")
        return leds

    def highlight_slot(self, slot_number, color="green", duration=10):
        leds = {}
        for slot in db.list_slots():
            if slot["slot_number"] == slot_number:
                leds[slot["led_number"]] = color
                break
        self._set_highlight(leds, duration, f"Подсветка слота {slot_number}")
        return leds

    def _set_highlight(self, leds, duration, message):
        with self.lock:
            self.highlight = {
                "until": time.monotonic() + duration,
                "leds": dict(leds),
                "message": message,
            }
            self.runtime["highlight"] = {
                "active": bool(leds),
                "leds": dict(leds),
                "message": message,
            }
            self.runtime["message"] = message if leds else "Нет ячеек для подсветки"

    def _clear_highlight(self):
        with self.lock:
            self.highlight = {"until": 0, "leds": {}, "message": None}
            self.runtime["highlight"] = {"active": False, "leds": {}, "message": None}
        self.highlight_was_active = False

    def _set_runtime(self, **values):
        with self.lock:
            self.runtime.update(values)
            if "last_tick" in values:
                self.last_tick_monotonic = time.monotonic()

    def _set_reader_runtime(self, channel, **values):
        with self.lock:
            readers = self.runtime.setdefault("readers", {})
            current = readers.setdefault(str(channel), {})
            current.update(values)

    def _load_settings(self):
        settings = db.get_settings()
        return {
            "brightness": self._int_setting(settings, "brightness", 80, 0, 255),
            "led_enabled": settings.get("led_enabled", "1") == "1",
            "switch_delay": self._float_setting(settings, "switch_delay", 0.08, 0.03, 1.0),
            "read_delay": self._float_setting(settings, "read_delay", 0.05, 0.0, 1.0),
            "read_timeout": self._float_setting(settings, "read_timeout", 0.18, 0.05, 2.0),
            "loop_delay": self._float_setting(settings, "loop_delay", 0.04, 0.02, 2.0),
            "reinit_delay": self._float_setting(settings, "reinit_delay", 1.0, 0.2, 10.0),
        }

    @staticmethod
    def _int_setting(settings, key, default, minimum, maximum):
        try:
            value = int(settings.get(key, default))
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))

    @staticmethod
    def _float_setting(settings, key, default, minimum, maximum):
        try:
            value = float(settings.get(key, default))
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))

    def _loop(self):
        self._set_runtime(running=True, message="Запуск hardware-цикла")
        try:
            self._setup_hardware()
            self._set_runtime(hardware_ready=True, message="Ридеры запущены")
            while not self.stop_event.is_set():
                settings = self._load_settings()
                slots = db.list_slots()

                if self.recheck_event.is_set():
                    self.readers.clear()
                    self.last_init_attempt.clear()
                    self.recheck_event.clear()

                if self.strip and self.current_brightness != settings["brightness"]:
                    try:
                        self.strip.setBrightness(settings["brightness"])
                        self.current_brightness = settings["brightness"]
                    except Exception as exc:
                        self._set_runtime(message=f"LED brightness error: {exc}")

                blink_on = int(time.monotonic() * 2) % 2 == 0
                for slot in slots:
                    if self.stop_event.is_set():
                        break
                    self._read_slot(slot, settings, blink_on)
                    time.sleep(settings["loop_delay"])

                self._render_highlight()
                self._set_runtime(last_tick=db.now_iso())
        except Exception as exc:
            self._set_runtime(
                hardware_ready=False,
                message=f"Hardware fatal: {exc}",
                last_traceback=traceback.format_exc(),
            )
        finally:
            self._safe_all_off()
            self._safe_disable_tca()
            self._set_runtime(running=False, hardware_ready=False)

    def _setup_hardware(self):
        import board
        import busio
        from rpi_ws281x import PixelStrip
        from smbus2 import SMBus

        self.selector = SMBus(I2C_BUS_NO)
        self._safe_disable_tca()

        self.strip = PixelStrip(
            LED_COUNT,
            LED_PIN,
            LED_FREQ_HZ,
            LED_DMA,
            LED_INVERT,
            self._load_settings()["brightness"],
            LED_CHANNEL,
        )
        self.strip.begin()
        self.current_brightness = self._load_settings()["brightness"]
        self._safe_all_off()

        self.i2c = busio.I2C(board.SCL, board.SDA)

    def _select_channel(self, channel, delay):
        self.selector.write_byte(TCA_ADDR, 1 << channel)
        time.sleep(delay)

    def _init_reader(self, slot, settings):
        from adafruit_pn532.i2c import PN532_I2C

        channel = slot["tca_channel"]
        now = time.monotonic()
        if now - self.last_init_attempt.get(channel, 0) < settings["reinit_delay"]:
            return None
        self.last_init_attempt[channel] = now

        try:
            self._select_channel(channel, settings["switch_delay"])
            reader = PN532_I2C(self.i2c, address=PN532_ADDR, debug=False)
            ic, ver, rev, support = reader.firmware_version
            reader.SAM_configuration()
            self.readers[channel] = reader
            self._set_reader_runtime(
                channel,
                online=True,
                firmware=f"{ver}.{rev}",
                ic=ic,
                support=support,
                error=None,
                slot_number=slot["slot_number"],
                led_number=slot["led_number"],
            )
            return reader
        except Exception as exc:
            self.readers[channel] = None
            self._set_reader_runtime(
                channel,
                online=False,
                error=str(exc),
                slot_number=slot["slot_number"],
                led_number=slot["led_number"],
            )
            self._apply_slot_state(slot, "error", None, None, f"Init: {exc}", blink_on=True)
            return None

    def _read_slot(self, slot, settings, blink_on):
        channel = slot["tca_channel"]
        reader = self.readers.get(channel) or self._init_reader(slot, settings)
        if reader is None:
            self.slot_read_cache.pop(slot["slot_number"], None)
            self._apply_slot_state(slot, "error", None, None, "Ридер не инициализирован", blink_on)
            return

        try:
            self._select_channel(channel, settings["switch_delay"])
            time.sleep(settings["read_delay"])
            uid = reader.read_passive_target(timeout=settings["read_timeout"])
            raw_uid = self._uid_to_str(uid) if uid else None
            uid_str, held, misses = self._stable_uid(slot["slot_number"], raw_uid)
            status, item, error = self._classify(slot["slot_number"], uid_str)
            self._apply_slot_state(slot, status, uid_str, item, error, blink_on)
            self._set_reader_runtime(channel, online=True, error=None, missed_reads=misses, held=held)
            if raw_uid:
                self._set_runtime(last_uid=raw_uid, last_uid_slot=slot["slot_number"])
        except Exception as exc:
            self.readers[channel] = None
            self.slot_read_cache.pop(slot["slot_number"], None)
            self._set_reader_runtime(channel, online=False, error=str(exc))
            self._apply_slot_state(slot, "error", None, None, f"Read: {exc}", blink_on)

    def _stable_uid(self, slot_number, uid):
        cache = self.slot_read_cache.setdefault(slot_number, {"uid": None, "misses": 0})

        if uid:
            cache["uid"] = uid
            cache["misses"] = 0
            return uid, False, 0

        cached_uid = cache.get("uid")
        if not cached_uid:
            cache["misses"] = 0
            return None, False, 0

        misses = int(cache.get("misses") or 0) + 1
        if misses < EMPTY_CONFIRM_READS:
            cache["misses"] = misses
            return cached_uid, True, misses

        cache["uid"] = None
        cache["misses"] = 0
        return None, False, misses

    @staticmethod
    def _uid_to_str(uid):
        return ":".join(f"{byte:02X}" for byte in uid)

    @staticmethod
    def _classify(slot_number, uid):
        if not uid:
            return "empty", None, None

        expected = db.get_item_for_slot(slot_number)
        known = db.get_item_by_uid(uid)
        if expected and expected["uid"] == uid:
            return "ok", expected, None
        if known:
            moved = db.move_item_to_slot(known["id"], slot_number)
            return "ok", moved or known, None
        return "unknown", None, "Метка не привязана"

    def _apply_slot_state(self, slot, status, uid, item, error, blink_on):
        slot_number = slot["slot_number"]
        db.set_slot_state(slot_number, status, uid, item, error)
        self._write_led(slot["led_number"], status, blink_on)

        signature = (status, uid, item["id"] if item else None, error)
        previous = self.last_signatures.get(slot_number)
        if previous is not None and previous != signature:
            self._log_transition(slot, status, uid, item, error)
        self.last_signatures[slot_number] = signature

    def _log_transition(self, slot, status, uid, item, error):
        item_name = item["name"] if item else None
        label = STATUS_LABELS.get(status, status)
        if status == "empty":
            event_type = "removed"
            message = f"{slot['name']}: пусто"
        elif status == "ok":
            event_type = "placed"
            message = f"{slot['name']}: {item_name} на месте"
        elif status == "wrong":
            event_type = "placed"
            message = f"{slot['name']}: чужая метка {uid}"
        elif status == "unknown":
            event_type = "unknown"
            message = f"{slot['name']}: неизвестная метка {uid}"
        else:
            event_type = "error"
            message = f"{slot['name']}: {error or label}"
        db.insert_event(slot["slot_number"], uid, event_type, status, item_name, message)

    def _write_led(self, led_number, status, blink_on):
        with self.lock:
            highlight = dict(self.highlight)
        if bool(highlight.get("leds")) and time.monotonic() < highlight.get("until", 0):
            return

        settings = self._load_settings()
        if not settings["led_enabled"]:
            return
        if not self.strip:
            return
        color = self._color(status, blink_on)
        index = led_number - 1
        try:
            self.strip.setPixelColor(index, color)
            self.strip.show()
        except Exception as exc:
            self._set_runtime(message=f"LED write error: {exc}")

    def _render_highlight(self):
        with self.lock:
            highlight = dict(self.highlight)
        active = bool(highlight.get("leds")) and time.monotonic() < highlight.get("until", 0)
        if not active:
            if self.highlight_was_active:
                self._safe_all_off()
                self._clear_highlight()
            return

        if not self.strip:
            return
        try:
            from rpi_ws281x import Color

            colors = {
                "blue": Color(0, 80, 255),
                "green": Color(0, 220, 80),
            }
            for index in range(LED_COUNT):
                self.strip.setPixelColor(index, Color(0, 0, 0))
            for led_number, color_name in highlight["leds"].items():
                self.strip.setPixelColor(led_number - 1, colors.get(color_name, colors["green"]))
            self.strip.show()
            self.highlight_was_active = True
        except Exception as exc:
            self._set_runtime(message=f"Highlight LED error: {exc}")

    @staticmethod
    def _color(status, blink_on):
        from rpi_ws281x import Color

        if status == "ok":
            return Color(0, 210, 90)
        if status in ("unknown", "wrong"):
            return Color(255, 190, 0)
        if status == "error":
            return Color(150, 70, 255) if blink_on else Color(0, 0, 0)
        return Color(255, 35, 30)

    def _safe_all_off(self):
        if not self.strip:
            return
        try:
            from rpi_ws281x import Color

            for index in range(LED_COUNT):
                self.strip.setPixelColor(index, Color(0, 0, 0))
            self.strip.show()
        except Exception:
            pass

    def _safe_disable_tca(self):
        if not self.selector:
            return
        try:
            self.selector.write_byte(TCA_ADDR, 0x00)
        except Exception:
            pass
