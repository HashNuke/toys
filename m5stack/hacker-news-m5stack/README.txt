Hacker News top five for M5Stack Core Basic

Build from this directory:
  uv run --project .. pio run -e news

First installation (ROM bootloader; installs the bootstrap and OTA partitions):
  uv run --project .. pio run -e bootstrap -t upload

Install or update the news app through the running software updater:
  uv run --project .. python upload_serial.py .pio/build/news/firmware.bin

First boot:
  Connect the board to your computer over USB.
  From m5stack/, run uv run python -m board_runtime.serial_wifi.
  Enter your 2.4 GHz network name and password at the prompts.
  The board tests the connection before saving credentials to flash; a failed
  connection restores the previous settings. Saved credentials survive power
  loss and are used automatically at boot. Run the tool again to change them.
  The app does not create a setup hotspot or use a fixed Wi-Fi password.
  You can also change credentials directly over signed, encrypted Bluetooth:
  from m5stack/, run uv run python -m board_runtime wifi_set.
  The Bluetooth client prompts for the SSID and hidden password.

Main screen:
  A: refresh now. B: read selected headline. C: select next headline.
Reading screen:
  A: return to list. B: next headline. C: next page for long headlines.

Fetches the first five IDs from the official HN topstories feed, in order.
Automatic refresh: five minutes. Failed fetches retry after thirty seconds.
HTTPS verifies Google's root certificates after NTP clock synchronization.
No API key, laptop relay, or subscription is needed.

Serial protocol, 115200 baud:
  HN:PING -> HN:PONG serial-update-v1
  HN:UPDATE <byte-count> <md5> -> HN:READY
  Send at most 1024 bytes, wait for HN:ACK <cumulative-byte-count>, repeat.
  Successful validation returns HN:DONE, selects the other OTA partition,
  and reboots. Incomplete or invalid transfers retain the existing app.
  This is an application updater, not the ESP32 ROM download protocol.
  New application builds must retain SerialUpdate.h to support future updates.

../m5stack-core-basic-firmware/hw-revision-unknown/original-fw-version-unknown/original-first-4mb.bin contains the original active flash layout.
The original partition table spans only the first 4 MB of the 16 MB chip.
Backup files may contain saved Wi-Fi credentials; keep them private.
See ../m5stack-core-basic-firmware/README.md for backup details.
Restore if necessary (replaces the installed news app):
  uv run --project .. python -m esptool --port /dev/cu.usbserial-01CDD34C --baud 230400 write_flash 0 ../m5stack-core-basic-firmware/hw-revision-unknown/original-fw-version-unknown/original-first-4mb.bin
