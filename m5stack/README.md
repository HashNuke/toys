# M5Stack projects

Run the commands below from this directory (`cd m5stack` from the repository
root). uv finds the shared `pyproject.toml` and `uv.lock` in the parent directory.

| Directory | Purpose |
| --- | --- |
| `hacker-news-m5stack/` | Hacker News reader app and software serial uploader |
| `wifi-diagnostics/` | ESP32 network diagnostics app |
| `m5stack-template/` | Starter app for new board programs |
| `shared-board-support/` | Shared C++ runtime, build settings, and OTA partition layout |
| `board_runtime/` | Python USB/Bluetooth clients, protocol implementation, and tests |
| `m5stack-core-basic-firmware/` | Documentation and ignored local images of the device's original firmware |

## Build and test

```sh
uv sync
uv run python -m pytest -q board_runtime/tests
uv run pio run -d hacker-news-m5stack -e news
uv run pio run -d m5stack-template -e template
uv run pio run -d wifi-diagnostics -e diagnostics
```

## Configure and control

```sh
uv run python -m board_runtime.serial_wifi
uv run python -m board_runtime status
uv run python -m board_runtime wifi_set
```

USB Wi-Fi configuration prompts for credentials. Bluetooth commands require the
existing enrolled sender key and device descriptor in the repository-root
`.devices/` directory (`../.devices/` from here). Reorganization does not require
reenrollment or key rotation. The local device identity header is kept in
`shared-board-support/identity/BoardIdentity.h`. Keys, identity headers, compiled files, and
flash snapshots are ignored by Git.

## Update the news app

```sh
uv run python hacker-news-m5stack/upload_serial.py hacker-news-m5stack/.pio/build/news/firmware.bin
```

All board apps use `shared-board-support/common.ini` and `BoardApp.h`, implementing
`appSetup()` and `appLoop()`. The shared runtime preserves OTA updates,
authenticated BLE commands, and USB Wi-Fi configuration with connection
validation and rollback. See each project's README for its specific commands.
