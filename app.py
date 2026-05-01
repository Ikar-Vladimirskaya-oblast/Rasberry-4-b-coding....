import atexit
import sqlite3

from flask import Flask, jsonify, render_template, request

import db
from cloud_sync import CloudSyncController
from hardware import HardwareController, STATUS_LABELS

app = Flask(__name__)
db.init_db()
controller = HardwareController()
controller.start()
cloud_sync = CloudSyncController()
cloud_sync.start()
atexit.register(controller.stop)
atexit.register(cloud_sync.stop)


def ok(payload=None, status=200):
    return jsonify(payload or {"ok": True}), status


def error(message, status=400):
    return jsonify({"ok": False, "error": message}), status


def normalize_uid(uid):
    if not uid:
        return ""
    cleaned = uid.strip().upper().replace("-", ":").replace(" ", ":")
    while "::" in cleaned:
        cleaned = cleaned.replace("::", ":")
    return cleaned


def item_payload(data):
    name = (data.get("name") or "").strip()
    uid = normalize_uid(data.get("uid") or "")
    note = (data.get("note") or "").strip()
    try:
        slot_number = int(data.get("slot_number"))
    except (TypeError, ValueError):
        slot_number = 0

    if not name:
        raise ValueError("Введите название предмета")
    if not uid:
        raise ValueError("Укажите UID метки")
    if slot_number not in (1, 2, 3, 4):
        raise ValueError("Выберите слот 1-4")
    return name, uid, slot_number, note


@app.route("/")
def index():
    return render_template("index.html")


@app.get("/api/state")
def api_state():
    slots = db.list_slots()
    for slot in slots:
        slot["status_label"] = STATUS_LABELS.get(slot["status"], slot["status"])
    return ok(
        {
            "slots": slots,
            "items": db.list_items(),
            "events": db.list_events(limit=30),
            "settings": db.get_settings(),
            "runtime": controller.snapshot(),
            "cloud": cloud_sync.snapshot(),
            "status_labels": STATUS_LABELS,
        }
    )


@app.get("/api/health")
def api_health():
    snapshot = controller.snapshot()
    status = 200 if snapshot.get("healthy") else 503
    return ok(
        {
            "healthy": snapshot.get("healthy"),
            "running": snapshot.get("running"),
            "hardware_ready": snapshot.get("hardware_ready"),
            "last_tick": snapshot.get("last_tick"),
            "message": snapshot.get("message"),
            "cloud": cloud_sync.snapshot(),
        },
        status=status,
    )


@app.get("/api/items")
def api_items():
    return ok({"items": db.list_items()})


@app.post("/api/items")
def api_create_item():
    try:
        name, uid, slot_number, note = item_payload(request.get_json(force=True))
        item_id = db.create_item(name, uid, slot_number, note)
        db.insert_event(slot_number, uid, "item", "created", name, f"Создан предмет {name}")
        return ok({"id": item_id})
    except sqlite3.IntegrityError as exc:
        if "idx_items_active_slot" in str(exc) or "items.slot_number" in str(exc):
            return error("В этом слоте уже есть активный предмет", 409)
        if "items.uid" in str(exc):
            return error("Эта UID-метка уже привязана", 409)
        return error(f"Ошибка базы: {exc}", 409)
    except ValueError as exc:
        return error(str(exc), 400)


@app.put("/api/items/<int:item_id>")
def api_update_item(item_id):
    try:
        name, uid, slot_number, note = item_payload(request.get_json(force=True))
        db.update_item(item_id, name, uid, slot_number, note)
        db.insert_event(slot_number, uid, "item", "updated", name, f"Обновлён предмет {name}")
        return ok()
    except sqlite3.IntegrityError as exc:
        if "idx_items_active_slot" in str(exc) or "items.slot_number" in str(exc):
            return error("В этом слоте уже есть активный предмет", 409)
        if "items.uid" in str(exc):
            return error("Эта UID-метка уже привязана", 409)
        return error(f"Ошибка базы: {exc}", 409)
    except ValueError as exc:
        return error(str(exc), 400)


@app.delete("/api/items/<int:item_id>")
def api_delete_item(item_id):
    db.deactivate_item(item_id)
    db.insert_event(None, None, "item", "deleted", None, f"Предмет #{item_id} отключён")
    return ok()


@app.post("/api/items/delete-by-uid")
def api_delete_item_by_uid():
    data = request.get_json(force=True) or {}
    uid = normalize_uid(data.get("uid") or "")
    if not uid:
        return error("UID is required", 400)

    item = db.deactivate_item_by_uid(uid)
    if item:
        db.insert_event(
            item["slot_number"],
            uid,
            "item",
            "deleted",
            item["name"],
            f"Item {uid} deleted from cloud",
        )
    return ok({"item": item})


@app.post("/api/items/cloud-save")
def api_cloud_save_item():
    try:
        name, uid, slot_number, note = item_payload(request.get_json(force=True) or {})
        item = db.upsert_item_by_uid(name, uid, slot_number, note, active=1)
        db.insert_event(slot_number, uid, "item", "saved", name, f"Item {name} saved from cloud")
        return ok({"item": item})
    except sqlite3.IntegrityError as exc:
        return error(f"DB error: {exc}", 409)
    except ValueError as exc:
        return error(str(exc), 400)


@app.post("/api/highlight/empty")
def api_highlight_empty():
    leds = controller.highlight_empty_unbound(duration=10)
    return ok({"leds": leds})


@app.post("/api/items/<int:item_id>/highlight")
def api_highlight_item(item_id):
    item = db.get_item_by_id(item_id)
    if not item:
        return error("Предмет не найден", 404)
    leds = controller.highlight_slot(item["slot_number"], color="green", duration=10)
    return ok({"leds": leds, "slot_number": item["slot_number"]})


@app.post("/api/highlight/slot/<int:slot_number>")
def api_highlight_slot(slot_number):
    if slot_number not in (1, 2, 3, 4):
        return error("Выберите слот 1-4", 400)
    leds = controller.highlight_slot(slot_number, color="green", duration=10)
    return ok({"leds": leds, "slot_number": slot_number})


@app.get("/api/events")
def api_events():
    slot = request.args.get("slot") or None
    query = request.args.get("q") or None
    return ok({"events": db.list_events(limit=120, slot_number=slot, query=query)})


@app.get("/api/cloud/status")
def api_cloud_status():
    return ok({"cloud": cloud_sync.snapshot()})


@app.get("/api/cloud/search")
def api_cloud_search():
    query = request.args.get("q") or ""
    try:
        limit = int(request.args.get("limit") or 50)
    except ValueError:
        limit = 50
    return ok(cloud_sync.search(query, limit=max(1, min(200, limit))))


@app.post("/api/settings")
def api_settings():
    data = request.get_json(force=True)
    values = {}
    if "brightness" in data:
        try:
            values["brightness"] = max(0, min(255, int(data["brightness"])))
        except (TypeError, ValueError):
            return error("Яркость должна быть числом 0-255")
    if "led_enabled" in data:
        values["led_enabled"] = "1" if bool(data["led_enabled"]) else "0"
    for key in ("switch_delay", "read_delay", "read_timeout", "loop_delay"):
        if key in data:
            try:
                values[key] = float(data[key])
            except (TypeError, ValueError):
                return error(f"{key} должно быть числом")
    db.update_settings(values)
    if "led_enabled" in values:
        controller.set_led_enabled(values["led_enabled"] == "1")
    return ok({"settings": db.get_settings()})


@app.post("/api/leds/off")
def api_leds_off():
    controller.set_led_enabled(False)
    return ok({"settings": db.get_settings()})


@app.post("/api/leds/on")
def api_leds_on():
    controller.set_led_enabled(True)
    return ok(
        {
            "settings": db.get_settings(),
            "message": "Статусная подсветка отключена, чтобы не было мигания. Используйте подсветку свободных ячеек или поиск.",
        }
    )


@app.post("/api/hardware/check")
def api_hardware_check():
    controller.request_recheck()
    return ok({"runtime": controller.snapshot()})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False, threaded=True)
