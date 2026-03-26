# Raspberry Pi RFID Local MVP

Local MVP for Raspberry Pi with PN532 readers, FastAPI, WebSocket updates,
SQLite event storage and a lightweight test GUI.

## Project structure

```text
.
|-- main.py
|-- desktop_app.py
|-- config.py
|-- requirements.txt
|-- readers.json
|-- readers.example.json
|-- readers.mock.json
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
|-- scripts/
|   |-- install_desktop_entry.sh
|   `-- run_desktop_app.sh
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
   sudo apt install -y python3-venv python3-pip python3-dev python3-smbus i2c-tools libgpiod3 python3-libgpiod python3-gi gir1.2-webkit2-4.1
   ```

2. Enable the hardware interface you need:

   ```bash
   sudo raspi-config
   ```

   Enable I2C, SPI, or UART in `Interface Options`.

   For the default real-hardware config in this repo, enable I2C.

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
./scripts/run_backend.sh
```

The service listens on `http://0.0.0.0:8000` by default.

If addressable LED mode is enabled, `scripts/run_backend.sh` escalates to
`sudo`, because `rpi_ws281x` needs low-level GPIO memory access on Raspberry Pi.

Open the GUI from another machine on the local network:

- `http://raspberrypi.local:8000`
- `http://<raspberry-ip>:8000`

## Real hardware quick start

The default `readers.json` in this repository is now configured for:

- `6 x PN532` over `I2C`
- `TCA9548A` multiplexer with auto-detect on bus addresses `0x70..0x77`
- PN532 bus address `0x24`
- reader channels `0..5`
- status LEDs disabled by default in the 6-reader config

If you want to go back to mock mode, copy `readers.mock.json` over
`readers.json` or export `APP_MOCK_ALL_READERS=true`.

## Wiring for Raspberry Pi 4 + PN532 + LED

Recommended mode for this repo: `I2C`

### TCA9548A to Raspberry Pi

Connect the multiplexer to the Raspberry Pi main I2C bus:

| Pin on TCA9548A | Connect to Raspberry Pi | GPIO | Physical pin |
|---|---|---:|---:|
| `VIN` | `3.3V` | - | `1` |
| `GND` | `GND` | - | `6` |
| `SDA` | `SDA1` | `GPIO2` | `3` |
| `SCL` | `SCL1` | `GPIO3` | `5` |

Default software behavior in this repo: auto-detect mux on `0x70..0x77`

### PN532 to TCA9548A

Each PN532 reader connects to its own TCA9548A channel:

- reader 1 -> channel `0`
- reader 2 -> channel `1`
- reader 3 -> channel `2`
- reader 4 -> channel `3`
- reader 5 -> channel `4`
- reader 6 -> channel `5`

For each PN532 on its channel:

- `VCC` -> `3.3V`
- `GND` -> `GND`
- `SDA` -> channel `SDx`
- `SCL` -> channel `SCx`

### Direct PN532 pin names

Your board is `ELECHOUSE NFC MODULE V3`. For I2C, use the pins that are
written directly on the module: `GND`, `VCC`, `SDA`, `SCL`, `RSTO`, `IRQ`.

| Pin on PN532 module | Connect to Raspberry Pi | GPIO | Physical pin |
|---|---|---:|---:|
| `VCC` | `3.3V` | - | `1` |
| `GND` | `GND` | - | `6` |
| `SDA` | `SDA1` | `GPIO2` | `3` |
| `SCL` | `SCL1` | `GPIO3` | `5` |
| `RSTO` | optional reset line | `GPIO25` | `22` |
| `IRQ` | optional request/interrupt | `GPIO24` | `18` |

Самая простая распиновка в одну строку:

- module `VCC` -> Pi pin `1`
- module `GND` -> Pi pin `6`
- module `SDA` -> Pi pin `3`
- module `SCL` -> Pi pin `5`
- module `RSTO` -> Pi pin `22` `optional`
- module `IRQ` -> Pi pin `18` `optional`

На самом модуле выставь переключатели режима в `I2C` по маркировке на плате
перед включением питания.

Если хочешь сначала проверить самый минимум, достаточно:

- `VCC`
- `GND`
- `SDA`
- `SCL`

Для мультиплексора в этом проекте `RSTO` и `IRQ` считаются опциональными,
потому что обычно разводят только питание и `SDA/SCL` через `TCA9548A`.

### Addressable LED to Raspberry Pi

- Raspberry Pi `GPIO18` (physical pin `12`) -> `330 Ohm resistor` -> LED `DIN`
- LED `5V` -> Raspberry Pi `5V` (physical pin `2` or `4`) for one pixel, or external `5V` PSU for a strip
- LED `GND` -> Raspberry Pi `GND` (for example physical pin `14`)
- If you use external `5V`, ground must stay common with Raspberry Pi

For reliable data level on real WS2812 strips, a `74AHCT125` or `74AHCT245`
level shifter between Raspberry Pi and `DIN` is recommended.

This matches the default config:

```json
"led_enabled": true,
"led_mode": "addressable",
"led_gpio_pin": 18,
"led_pixel_count": 1,
"led_pixel_index": 0,
"led_brightness": 64
```

If several readers share one LED strip, keep the same `led_gpio_pin` and
`led_pixel_count`, but assign each reader its own `led_pixel_index`.

## Desktop app on Raspberry Pi

The project now has a real desktop shell, not a browser tab disguised as an
application. By default it launches the local GUI in `chromium --app` mode,
which is more stable on Raspberry Pi touchscreens and small HDMI panels.
If Chromium is unavailable, it falls back to the native `pywebview` shell.

```bash
chmod +x scripts/run_backend.sh scripts/run_desktop_app.sh scripts/install_desktop_entry.sh
./scripts/run_desktop_app.sh
```

This script:

- starts the FastAPI backend if it is not already running,
- waits until `http://127.0.0.1:8000` is ready,
- opens the GUI in a dedicated Chromium app window,
- falls back to `desktop_app.py` only if Chromium is not available.

If addressable LED mode is enabled, start the backend once from terminal with:

```bash
./scripts/run_backend.sh
```

or explicitly:

```bash
sudo ./scripts/run_backend.sh
```

To install a desktop icon on Raspberry Pi:

```bash
./scripts/install_desktop_entry.sh
```

This creates `RFID Local MVP` launchers in `~/Desktop` and
`~/.local/share/applications`.

Desktop app files:

- `desktop_app.py` is the fallback native window entrypoint.
- `scripts/run_desktop_app.sh` starts backend + desktop window.
- `scripts/run_backend.sh` starts the backend and escalates to root when
  addressable LEDs require low-level GPIO access.

If you want to force the old native shell for debugging:

```bash
DESKTOP_APP_ENGINE=pywebview ./scripts/run_desktop_app.sh
```

## Debian package

For Raspberry Pi OS the recommended distributable format is `.deb`, not
AppImage. This repository can build an installable Debian package with:

```bash
chmod +x scripts/build_deb.sh
./scripts/build_deb.sh --version 0.1.0
```

The package will be written to `./dist`, for example:

```text
dist/rfid-local-mvp_0.1.0_arm64.deb
```

What the `.deb` installs:

- application files in `/opt/rfid-local-mvp`
- editable config in `/etc/rfid-local-mvp/readers.json`
- SQLite data in `/var/lib/rfid-local-mvp/events.db`
- systemd service `rfid-local-mvp.service`
- menu entry and desktop launcher `RFID Local MVP`

To install on Raspberry Pi:

```bash
sudo apt install ./dist/rfid-local-mvp_0.1.0_arm64.deb
```

The installer bootstraps the Python runtime in `/opt/rfid-local-mvp/.venv`.
If wheels were bundled during build, installation works without downloading
Python packages from the internet.

## Mock mode

The repository default is now real hardware mode. For development without
PN532, use `readers.mock.json` as a ready-made mock config file.

Two ways to force mock mode:

1. Copy `readers.mock.json` over `readers.json` or set `"mock_mode": true`
   for a reader in `readers.json`.
2. Export an environment variable to force all readers into mock mode:

   ```bash
   export APP_MOCK_ALL_READERS=true
   ./scripts/run_backend.sh
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
    "name": "PN532 Main Reader",
    "type": "pn532",
    "interface": "i2c",
    "enabled": true,
    "mock_mode": false,
    "poll_interval": 0.2,
    "scan_cooldown_seconds": 2.0,
    "reconnect_interval": 5.0,
    "i2c_address": "0x24",
    "reset_pin": "D25",
    "req_pin": "D24",
    "led_enabled": true,
    "led_mode": "addressable",
    "led_gpio_pin": 18,
    "led_pixel_count": 1,
    "led_pixel_index": 0,
    "led_brightness": 64
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

- For `ELECHOUSE NFC MODULE V3`, I2C is the simplest wiring because the
  module already exposes `VCC/GND/SDA/SCL` as a dedicated header.
- For I2C, the Adafruit driver works best when both `RSTO` and `IRQ`
  are physically connected and declared as `reset_pin` and `req_pin`.
- The GUI now shows the configured addressable LED pin and pixel index.
- `GPIO18` is the default output for the addressable LED status pixel.
- If a reader is disconnected or fails during startup, the backend keeps
  running and retries initialization in the background.

## Quick verification without PN532

1. Keep `mock_mode` enabled in `readers.json`.
2. Start the app.
3. Open the GUI in a browser.
4. Click `Scan test`.
5. Confirm that the last UID updates and a new event appears in the log.
