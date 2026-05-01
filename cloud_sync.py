import asyncio
import json
import threading
import time
import uuid
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

import db


class CloudSyncController:
    def __init__(self):
        self.stop_event = threading.Event()
        self.thread = None
        self.lock = threading.Lock()
        self.runtime = {
            "enabled": False,
            "connected": False,
            "last_sync": None,
            "last_error": None,
            "last_message": "Cloud sync не запущен",
            "server_url": None,
            "device_id": None,
            "uploaded": None,
            "downloaded": None,
        }

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._thread_main, name="cloud-sync", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)

    def snapshot(self):
        with self.lock:
            data = dict(self.runtime)
        data["running"] = bool(self.thread and self.thread.is_alive())
        return data

    def search(self, query, limit=50):
        settings = db.get_settings()
        if settings.get("cloud_enabled", "0") != "1":
            local = db.search_local(query, limit=limit)
            local["source"] = "sqlite"
            return local

        try:
            base_url = self._http_base_url(settings)
            device_id = settings.get("cloud_device_id") or "raspberry-organizer"
            params = urlencode({"q": query, "device_id": device_id, "limit": int(limit)})
            with urlopen(f"{base_url}/api/search?{params}", timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))
                data["source"] = "postgres"
                return data
        except Exception as exc:
            local = db.search_local(query, limit=limit)
            local["source"] = "sqlite"
            local["cloud_error"] = str(exc)
            self._set_runtime(last_error=str(exc), connected=False)
            return local

    def _thread_main(self):
        while not self.stop_event.is_set():
            settings = db.get_settings()
            enabled = settings.get("cloud_enabled", "0") == "1"
            self._set_runtime(
                enabled=enabled,
                server_url=settings.get("cloud_url"),
                device_id=settings.get("cloud_device_id"),
            )
            if not enabled:
                self._set_runtime(connected=False, last_message="Cloud sync выключен")
                self._wait(5)
                continue

            try:
                asyncio.run(self._connect_once())
            except Exception as exc:
                self._set_runtime(
                    connected=False,
                    last_error=str(exc),
                    last_message="Нет связи с cloud, работаем офлайн",
                )
                self._wait(8)

    async def _connect_once(self):
        try:
            import websockets
        except ImportError as exc:
            raise RuntimeError("Не установлен пакет websockets") from exc

        settings = db.get_settings()
        url = settings.get("cloud_url") or "ws://141.105.68.221:8091/ws/raspberry-organizer"
        interval = self._float_setting(settings.get("cloud_sync_interval"), 8, 3, 120)
        device_id = settings.get("cloud_device_id") or "raspberry-organizer"

        async with websockets.connect(url, ping_interval=20, ping_timeout=10, close_timeout=5) as websocket:
            self._set_runtime(
                connected=True,
                last_error=None,
                last_message="Cloud sync подключен",
                server_url=url,
                device_id=device_id,
            )
            await self._recv_any(websocket, timeout=5)

            while not self.stop_event.is_set():
                await self._sync_once(websocket, device_id)
                await self._idle(websocket, interval)

    async def _sync_once(self, websocket, device_id):
        snapshot_id = str(uuid.uuid4())
        payload = db.export_sync_snapshot(device_name=device_id)
        await websocket.send(
            json.dumps(
                {
                    "type": "snapshot",
                    "request_id": snapshot_id,
                    "payload": payload,
                },
                ensure_ascii=False,
                default=str,
            )
        )
        ack = await self._recv_matching(websocket, snapshot_id, timeout=12)

        state_id = str(uuid.uuid4())
        await websocket.send(
            json.dumps(
                {
                    "type": "state_request",
                    "request_id": state_id,
                    "payload": {},
                },
                ensure_ascii=False,
            )
        )
        state_message = await self._recv_matching(websocket, state_id, timeout=12)
        downloaded = {}
        if state_message.get("type") == "state":
            downloaded = db.apply_cloud_state(state_message.get("state") or {})

        now = db.now_iso()
        self._set_runtime(
            connected=True,
            last_sync=now,
            last_error=None,
            last_message="SQLite и PostgreSQL синхронизированы",
            uploaded=ack.get("synced"),
            downloaded=downloaded,
        )

    async def _recv_any(self, websocket, timeout):
        try:
            raw = await asyncio.wait_for(websocket.recv(), timeout=timeout)
            return json.loads(raw)
        except asyncio.TimeoutError:
            return None

    async def _recv_matching(self, websocket, request_id, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and not self.stop_event.is_set():
            raw = await asyncio.wait_for(websocket.recv(), timeout=max(0.2, deadline - time.monotonic()))
            message = json.loads(raw)
            if message.get("type") in ("ping", "command"):
                await self._handle_server_message(websocket, message)
                continue
            if message.get("request_id") == request_id:
                if message.get("type") == "error":
                    raise RuntimeError(message.get("error") or "Cloud sync error")
                return message
        raise TimeoutError("Cloud sync response timeout")

    async def _idle(self, websocket, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end and not self.stop_event.is_set():
            try:
                raw = await asyncio.wait_for(websocket.recv(), timeout=min(0.5, end - time.monotonic()))
            except asyncio.TimeoutError:
                continue
            await self._handle_server_message(websocket, json.loads(raw))

    async def _handle_server_message(self, websocket, message):
        if message.get("type") == "ping":
            await websocket.send(json.dumps({"type": "pong", "request_id": message.get("request_id")}))
            return
        if message.get("type") != "command":
            return

        request_id = message.get("request_id")
        command = message.get("command")
        payload = message.get("payload") or {}
        try:
            result = self._run_local_command(command, payload)
            body = {"ok": True, "command": command, "response": result}
        except Exception as exc:
            body = {"ok": False, "command": command, "error": str(exc)}

        await websocket.send(
            json.dumps(
                {
                    "type": "command_result",
                    "request_id": request_id,
                    "payload": body,
                },
                ensure_ascii=False,
            )
        )

    def _run_local_command(self, command, payload):
        if command == "highlight_empty":
            return self._post_local("/api/highlight/empty")
        if command == "highlight_slot":
            slot_number = int(payload.get("slot_number"))
            return self._post_local(f"/api/highlight/slot/{slot_number}")
        if command == "leds_off":
            return self._post_local("/api/leds/off")
        if command == "hardware_check":
            return self._post_local("/api/hardware/check")
        if command == "delete_item":
            uid = payload.get("uid")
            if not uid:
                raise ValueError("UID is required")
            return self._post_local("/api/items/delete-by-uid", {"uid": uid})
        if command == "save_item":
            return self._post_local("/api/items/cloud-save", payload)
        raise ValueError(f"Unknown command: {command}")

    @staticmethod
    def _post_local(path, payload=None):
        request = Request(
            f"http://127.0.0.1:5000{path}",
            data=json.dumps(payload or {}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=8) as response:
            return json.loads(response.read().decode("utf-8"))

    def _wait(self, seconds):
        self.stop_event.wait(seconds)

    def _set_runtime(self, **values):
        with self.lock:
            self.runtime.update(values)

    @staticmethod
    def _float_setting(value, default, minimum, maximum):
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = default
        return max(minimum, min(maximum, parsed))

    @staticmethod
    def _http_base_url(settings):
        cloud_url = settings.get("cloud_url") or "ws://141.105.68.221:8091/ws/raspberry-organizer"
        parsed = urlparse(cloud_url)
        scheme = "https" if parsed.scheme == "wss" else "http"
        return f"{scheme}://{parsed.netloc}"
