import sqlite3
from datetime import datetime, timezone

from config import DATABASE_PATH, DEFAULT_SETTINGS, SLOTS


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_time(value):
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def cloud_is_newer(cloud_value, local_value):
    cloud_dt = parse_time(cloud_value)
    local_dt = parse_time(local_value)
    if cloud_dt is None:
        return False
    if local_dt is None:
        return True
    return cloud_dt >= local_dt


def bool_int(value, default=1):
    if value is None:
        return default
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, (int, float)):
        return 1 if value else 0
    return 0 if str(value).strip().lower() in ("0", "false", "no", "off", "") else 1


def connect():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def row_to_dict(row):
    return dict(row) if row is not None else None


def init_db():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS slots (
                slot_number INTEGER PRIMARY KEY,
                tca_channel INTEGER NOT NULL,
                led_number INTEGER NOT NULL,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'empty',
                current_uid TEXT,
                current_item_id INTEGER,
                current_item_name TEXT,
                error TEXT,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                uid TEXT NOT NULL UNIQUE,
                slot_number INTEGER NOT NULL REFERENCES slots(slot_number),
                note TEXT NOT NULL DEFAULT '',
                active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE UNIQUE INDEX IF NOT EXISTS idx_items_active_slot
                ON items(slot_number)
                WHERE active = 1;

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                slot_number INTEGER,
                uid TEXT,
                event_type TEXT NOT NULL,
                result TEXT NOT NULL,
                item_name TEXT,
                message TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS cloud_event_map (
                server_event_id INTEGER PRIMARY KEY,
                local_event_id INTEGER,
                synced_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sync_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )

        for slot in SLOTS:
            conn.execute(
                """
                INSERT INTO slots (slot_number, tca_channel, led_number, name, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(slot_number) DO UPDATE SET
                    tca_channel = excluded.tca_channel,
                    led_number = excluded.led_number,
                    name = excluded.name
                """,
                (
                    slot["slot_number"],
                    slot["tca_channel"],
                    slot["led_number"],
                    slot["name"],
                    now_iso(),
                ),
            )

        for key, value in DEFAULT_SETTINGS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                (key, value),
            )


def get_settings():
    with connect() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {row["key"]: row["value"] for row in rows}


def set_setting(key, value):
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, str(value)),
        )


def update_settings(values):
    with connect() as conn:
        for key, value in values.items():
            conn.execute(
                """
                INSERT INTO settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, str(value)),
            )


def get_sync_meta(key, default=None):
    with connect() as conn:
        row = conn.execute("SELECT value FROM sync_meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_sync_meta(key, value):
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO sync_meta (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, str(value)),
        )


def list_slots():
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                s.*,
                i.id AS expected_item_id,
                i.name AS expected_item_name,
                i.uid AS expected_uid,
                i.note AS expected_note
            FROM slots s
            LEFT JOIN items i
                ON i.slot_number = s.slot_number
               AND i.active = 1
            ORDER BY s.slot_number
            """
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def get_slot_by_channel(channel):
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM slots WHERE tca_channel = ?",
            (channel,),
        ).fetchone()
    return row_to_dict(row)


def set_slot_state(slot_number, status, uid=None, item=None, error=None):
    item_id = item["id"] if item else None
    item_name = item["name"] if item else None
    with connect() as conn:
        conn.execute(
            """
            UPDATE slots
               SET status = ?,
                   current_uid = ?,
                   current_item_id = ?,
                   current_item_name = ?,
                   error = ?,
                   updated_at = ?
             WHERE slot_number = ?
            """,
            (status, uid, item_id, item_name, error, now_iso(), slot_number),
        )


def get_item_by_uid(uid, include_inactive=False):
    if not uid:
        return None
    active_clause = "" if include_inactive else "AND active = 1"
    with connect() as conn:
        row = conn.execute(
            f"SELECT * FROM items WHERE uid = ? {active_clause}",
            (uid,),
        ).fetchone()
    return row_to_dict(row)


def get_item_by_id(item_id):
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM items WHERE id = ? AND active = 1",
            (item_id,),
        ).fetchone()
    return row_to_dict(row)


def get_item_for_slot(slot_number):
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM items WHERE slot_number = ? AND active = 1",
            (slot_number,),
        ).fetchone()
    return row_to_dict(row)


def list_items(include_inactive=False):
    where = "" if include_inactive else "WHERE active = 1"
    with connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM items {where} ORDER BY active DESC, slot_number, name"
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def create_item(name, uid, slot_number, note=""):
    ts = now_iso()
    with connect() as conn:
        existing = conn.execute(
            "SELECT id FROM items WHERE uid = ? AND active = 0",
            (uid,),
        ).fetchone()
        if existing:
            conn.execute(
                """
                UPDATE items
                   SET name = ?,
                       slot_number = ?,
                       note = ?,
                       active = 1,
                       updated_at = ?
                 WHERE id = ?
                """,
                (name, slot_number, note, ts, existing["id"]),
            )
            return existing["id"]

        cur = conn.execute(
            """
            INSERT INTO items (name, uid, slot_number, note, active, created_at, updated_at)
            VALUES (?, ?, ?, ?, 1, ?, ?)
            """,
            (name, uid, slot_number, note, ts, ts),
        )
        return cur.lastrowid


def update_item(item_id, name, uid, slot_number, note=""):
    with connect() as conn:
        conn.execute(
            """
            UPDATE items
               SET name = ?,
                   uid = ?,
                   slot_number = ?,
                   note = ?,
                   updated_at = ?
             WHERE id = ? AND active = 1
            """,
            (name, uid, slot_number, note, now_iso(), item_id),
        )


def upsert_item_by_uid(name, uid, slot_number, note="", active=1):
    ts = now_iso()
    with connect() as conn:
        existing = conn.execute(
            "SELECT * FROM items WHERE uid = ?",
            (uid,),
        ).fetchone()
        if active:
            conn.execute(
                """
                UPDATE items
                   SET active = 0,
                       updated_at = ?
                 WHERE slot_number = ?
                   AND uid != ?
                   AND active = 1
                """,
                (ts, slot_number, uid),
            )

        if existing:
            conn.execute(
                """
                UPDATE items
                   SET name = ?,
                       slot_number = ?,
                       note = ?,
                       active = ?,
                       updated_at = ?
                 WHERE uid = ?
                """,
                (name, slot_number, note, bool_int(active), ts, uid),
            )
        else:
            conn.execute(
                """
                INSERT INTO items (name, uid, slot_number, note, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (name, uid, slot_number, note, bool_int(active), ts, ts),
            )
        row = conn.execute("SELECT * FROM items WHERE uid = ?", (uid,)).fetchone()
    return row_to_dict(row)


def move_item_to_slot(item_id, slot_number):
    ts = now_iso()
    with connect() as conn:
        moving = conn.execute(
            "SELECT * FROM items WHERE id = ? AND active = 1",
            (item_id,),
        ).fetchone()
        if moving is None:
            return None

        old_slot = moving["slot_number"]
        if old_slot == slot_number:
            return row_to_dict(moving)

        occupant = conn.execute(
            """
            SELECT * FROM items
             WHERE slot_number = ?
               AND active = 1
               AND id != ?
            """,
            (slot_number, item_id),
        ).fetchone()

        conn.execute(
            "UPDATE items SET active = 0, updated_at = ? WHERE id = ?",
            (ts, item_id),
        )
        if occupant is not None:
            conn.execute(
                "UPDATE items SET slot_number = ?, updated_at = ? WHERE id = ?",
                (old_slot, ts, occupant["id"]),
            )
        conn.execute(
            """
            UPDATE items
               SET slot_number = ?,
                   active = 1,
                   updated_at = ?
             WHERE id = ?
            """,
            (slot_number, ts, item_id),
        )
        moved = conn.execute(
            "SELECT * FROM items WHERE id = ?",
            (item_id,),
        ).fetchone()
        return row_to_dict(moved)


def deactivate_item(item_id):
    with connect() as conn:
        conn.execute(
            "UPDATE items SET active = 0, updated_at = ? WHERE id = ?",
            (now_iso(), item_id),
        )


def deactivate_item_by_uid(uid):
    ts = now_iso()
    with connect() as conn:
        conn.execute(
            "UPDATE items SET active = 0, updated_at = ? WHERE uid = ?",
            (ts, uid),
        )
        row = conn.execute(
            "SELECT * FROM items WHERE uid = ?",
            (uid,),
        ).fetchone()
    return row_to_dict(row)


def insert_event(slot_number, uid, event_type, result, item_name, message):
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO events
                (created_at, slot_number, uid, event_type, result, item_name, message)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (now_iso(), slot_number, uid, event_type, result, item_name, message),
        )


def list_events(limit=80, slot_number=None, query=None):
    clauses = []
    params = []
    if slot_number:
        clauses.append("slot_number = ?")
        params.append(int(slot_number))
    if query:
        clauses.append("(uid LIKE ? OR item_name LIKE ? OR message LIKE ?)")
        like = f"%{query}%"
        params.extend([like, like, like])

    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    params.append(int(limit))
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM events
            {where}
            ORDER BY id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [row_to_dict(row) for row in rows]


def export_sync_snapshot(device_name="Raspberry Organizer", event_limit=300):
    return {
        "device_name": device_name,
        "slots": list_slots(),
        "items": list_items(include_inactive=True),
        "events": list_events(limit=event_limit),
        "settings": get_settings(),
    }


def import_cloud_item(item):
    uid = item.get("uid")
    if not uid:
        return "skipped"

    ts = item.get("updated_at") or now_iso()
    active = bool_int(item.get("active"), 1)
    slot_number = int(item.get("slot_number") or 1)
    name = item.get("name") or "Без названия"
    note = item.get("note") or ""
    created_at = item.get("created_at") or ts

    with connect() as conn:
        existing = conn.execute("SELECT * FROM items WHERE uid = ?", (uid,)).fetchone()

        if existing and not cloud_is_newer(ts, existing["updated_at"]):
            return "kept"

        if active:
            conn.execute(
                """
                UPDATE items
                   SET active = 0,
                       updated_at = ?
                 WHERE slot_number = ?
                   AND uid != ?
                   AND active = 1
                """,
                (now_iso(), slot_number, uid),
            )

        if existing:
            conn.execute(
                """
                UPDATE items
                   SET name = ?,
                       slot_number = ?,
                       note = ?,
                       active = ?,
                       updated_at = ?
                 WHERE uid = ?
                """,
                (name, slot_number, note, active, ts, uid),
            )
            return "updated"

        conn.execute(
            """
            INSERT INTO items (name, uid, slot_number, note, active, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (name, uid, slot_number, note, active, created_at, ts),
        )
        return "created"


def import_cloud_settings(settings):
    allowed = {
        key: value
        for key, value in (settings or {}).items()
        if not str(key).startswith("cloud_")
    }
    if not allowed:
        return 0
    update_settings(allowed)
    return len(allowed)


def import_cloud_event(event):
    server_id = event.get("id")
    if not server_id:
        return "skipped"

    local_id = event.get("local_id")
    with connect() as conn:
        mapped = conn.execute(
            "SELECT local_event_id FROM cloud_event_map WHERE server_event_id = ?",
            (server_id,),
        ).fetchone()
        if mapped:
            return "kept"

        if local_id:
            existing = conn.execute("SELECT id FROM events WHERE id = ?", (local_id,)).fetchone()
            if existing:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO cloud_event_map (server_event_id, local_event_id, synced_at)
                    VALUES (?, ?, ?)
                    """,
                    (server_id, local_id, now_iso()),
                )
                return "mapped"

        cur = conn.execute(
            """
            INSERT INTO events
                (created_at, slot_number, uid, event_type, result, item_name, message)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.get("created_at") or now_iso(),
                event.get("slot_number"),
                event.get("uid"),
                event.get("event_type") or "",
                event.get("result") or "",
                event.get("item_name"),
                event.get("message") or "",
            ),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO cloud_event_map (server_event_id, local_event_id, synced_at)
            VALUES (?, ?, ?)
            """,
            (server_id, cur.lastrowid, now_iso()),
        )
        return "created"


def import_cloud_slot_metadata(slot):
    slot_number = slot.get("slot_number")
    if not slot_number:
        return "skipped"
    with connect() as conn:
        existing = conn.execute(
            "SELECT updated_at FROM slots WHERE slot_number = ?",
            (slot_number,),
        ).fetchone()
        if existing and not cloud_is_newer(slot.get("updated_at"), existing["updated_at"]):
            return "kept"
        conn.execute(
            """
            UPDATE slots
               SET name = COALESCE(?, name),
                   updated_at = COALESCE(?, updated_at)
             WHERE slot_number = ?
            """,
            (slot.get("name"), slot.get("updated_at"), slot_number),
        )
        return "updated"


def apply_cloud_state(state):
    counters = {
        "items_created": 0,
        "items_updated": 0,
        "items_kept": 0,
        "events_created": 0,
        "events_kept": 0,
        "slots_updated": 0,
        "settings": 0,
    }

    for item in state.get("items") or []:
        result = import_cloud_item(item)
        if result == "created":
            counters["items_created"] += 1
        elif result == "updated":
            counters["items_updated"] += 1
        elif result == "kept":
            counters["items_kept"] += 1

    for slot in state.get("slots") or []:
        if import_cloud_slot_metadata(slot) == "updated":
            counters["slots_updated"] += 1

    for event in state.get("events") or []:
        result = import_cloud_event(event)
        if result == "created":
            counters["events_created"] += 1
        elif result in ("kept", "mapped"):
            counters["events_kept"] += 1

    counters["settings"] = import_cloud_settings(state.get("settings") or {})
    set_sync_meta("cloud_last_sync", now_iso())
    return counters


def search_local(query, limit=50):
    like = f"%{query}%"
    with connect() as conn:
        items = conn.execute(
            """
            SELECT * FROM items
             WHERE active = 1
               AND (name LIKE ? OR uid LIKE ? OR note LIKE ?)
             ORDER BY updated_at DESC
             LIMIT ?
            """,
            (like, like, like, int(limit)),
        ).fetchall()
        slots = conn.execute(
            """
            SELECT * FROM slots
             WHERE name LIKE ? OR COALESCE(current_uid, '') LIKE ? OR status LIKE ?
             ORDER BY updated_at DESC
             LIMIT ?
            """,
            (like, like, like, int(limit)),
        ).fetchall()
    return {
        "query": query,
        "items": [row_to_dict(row) for row in items],
        "slots": [row_to_dict(row) for row in slots],
    }
