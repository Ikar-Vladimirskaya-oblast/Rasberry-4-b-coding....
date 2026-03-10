# Raspberry Pi RFID Local MVP

Local MVP for Raspberry Pi with PN532 readers, FastAPI, WebSocket updates,
SQLite event storage and a lightweight test GUI.

## Project structure

```text
.
|-- main.py
|-- config.py
|-- requirements.txt
|-- readers.json
|-- readers.example.json
|-- models/
|   |-- __init__.py
|   |-- events.py
|   `-- readers.py
|-- routes/
|   |-- __init__.py
|   |-- api.py
|   `-- gui.py
|-- services/
|   |-- __init__.py
|   |-- reader_manager.py
|   |-- websocket_manager.py
|   `-- readers/
|       |-- __init__.py
|       |-- base.py
|       `-- pn532.py
|-- static/
|   |-- app.js
|   `-- styles.css
|-- storage/
|   |-- __init__.py
|   `-- database.py
`-- templates/
    `-- index.html
```

## Features

- FastAPI backend with HTTP API and WebSocket endpoint.
- PN532 abstraction with `ReaderBase`, `PN532Reader`, and `ReaderManager`.
- SQLite event log with `system_started`, `reader_initialized`,
  `card_detected`, `reader_error`, and `reader_disconnected`.
- Browser GUI with realtime updates for system state, readers and logs.
- Mock mode for development without PN532 hardware.
- Anti-duplicate filter for repeated UID reads from the same reader.

## Requirements

- Python 3.10+
- Raspberry Pi OS or another Debian-based Linux on Raspberry Pi
- PN532 wired over I2C, SPI, or UART if you want real hardware scans

## Raspberry Pi setup

1. Update packages:

   ```bash
   sudo apt update
   sudo apt install -y python3-venv python3-pip python3-dev python3-smbus i2c-tools libgpiod2
   ```

2. Enable the hardware interface you need:

   ```bash
   sudo raspi-config
   ```

   Enable I2C, SPI, or UART in `Interface Options`.

3. Create a virtual environment and install dependencies:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

## Run the project

```bash
source .venv/bin/activate
python main.py
```

The service listens on `http://0.0.0.0:8000` by default.

Open the GUI from another machine on the local network:

- `http://raspberrypi.local:8000`
- `http://<raspberry-ip>:8000`

## Mock mode

The default `readers.json` starts in mock mode so the GUI and backend work
without PN532 hardware.

Two ways to force mock mode:

1. Set `"mock_mode": true` for a reader in `readers.json`.
2. Export an environment variable to force all readers into mock mode:

   ```bash
   export APP_MOCK_ALL_READERS=true
   python main.py
   ```

In mock mode:

- the backend starts normally even if PN532 is absent,
- the reader is shown as `connected` with `mode=mock`,
- the `Scan test` button generates a mock UID event,
- events are written to SQLite and pushed through WebSocket.

## Configure readers

`readers.json` contains a list of reader definitions. Example:

```json
[
  {
    "id": "reader_1",
    "name": "Test Reader 1",
    "type": "pn532",
    "interface": "i2c",
    "enabled": true,
    "mock_mode": false,
    "poll_interval": 0.5,
    "scan_cooldown_seconds": 2.0,
    "reconnect_interval": 5.0,
    "i2c_address": "0x24",
    "reset_pin": "D6",
    "req_pin": "D12"
  }
]
```

To add another reader, append a second object with a unique `id`.
The architecture already supports a list of readers and independent polling.

## API

- `GET /api/status` returns system state and all readers.
- `GET /api/readers` returns reader list.
- `GET /api/logs` returns the latest 100 events.
- `POST /api/readers/{reader_id}/scan` performs a manual scan test.
- `POST /api/readers/{reader_id}/reset` reinitializes a reader.
- `GET /` serves the test GUI.
- `/ws` is the WebSocket endpoint.

## Logs and storage

- SQLite file: `storage/events.db`
- Console logs show startup, reader init, reconnect attempts, UID detections
  and WebSocket connections.
- Event history can be read from the GUI or with:

  ```bash
  curl http://127.0.0.1:8000/api/logs
  ```

## Hardware notes

- For Raspberry Pi, SPI is usually the most reliable PN532 interface.
- For I2C, the Adafruit driver works best when `reset_pin` and `req_pin`
  are both connected and declared in `readers.json`.
- If a reader is disconnected or fails during startup, the backend keeps
  running and retries initialization in the background.

## Quick verification without PN532

1. Keep `mock_mode` enabled in `readers.json`.
2. Start the app.
3. Open the GUI in a browser.
4. Click `Scan test`.
5. Confirm that the last UID updates and a new event appears in the log.
