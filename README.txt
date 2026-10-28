toys

A playground for hardware experiments and small projects.
Python 3.12 and Python dependencies are managed with uv.

  uv sync
  cd m5stack
  uv run pio run -d hacker-news-m5stack -e news
  uv run python hacker-news-m5stack/upload_serial.py hacker-news-m5stack/.pio/build/news/firmware.bin

All board-related projects live in m5stack/. Run the commands below from that
directory; see m5stack/README.md for the project layout and build commands.
The Hacker News project's README.txt describes Wi-Fi setup, buttons, initial
installation, the serial updater, and restoration of the original firmware.

Every future board app inherits shared-board-support/common.ini and BoardApp.h; copy
m5stack-template as a starting point. board_runtime/README.txt documents the
signed, encrypted Bluetooth command client and shared sender key.

  uv run python -m board_runtime status
  uv run python -m board_runtime wifi_set
  uv run python -m board_runtime.serial_wifi

Build artifacts, virtual environments, and private firmware backups are ignored
by Git. Add future experiments in their own directories.

Wi-Fi diagnostics through the ESP32, without changing the laptop's network:
  uv run pio run -d wifi-diagnostics
  uv run python -m board_runtime.diagnostics probe
  uv run python -m board_runtime.diagnostic_bridge
See wifi-diagnostics/README.txt for serial commands, HTTP relay, and idle tests.
