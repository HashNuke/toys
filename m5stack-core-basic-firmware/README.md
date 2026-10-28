# M5Stack Core Basic original firmware

These private flash snapshots were saved before installing this project's custom
firmware. They belong to this device:

| Property | Identification |
| --- | --- |
| Device model | M5Stack Core Basic, as identified in the project documentation |
| Board ID / MAC | `240ac45b5a4c` / `24:0a:c4:5b:5a:4c` |
| PlatformIO board target | `m5stack-core-esp32` |
| Flash capacity | 16 MiB, as recorded in the project documentation |
| Hardware revision | Unknown; not established by the saved metadata |
| Original firmware name/version | Unknown; no release identifier found in the backup |
| Snapshot file date | 2026-10-11, from the existing files' modification timestamps |

The PlatformIO target is a build target, not a hardware revision. The original
firmware is the software present when these snapshots were taken; its vendor
and factory provenance have not been verified. It is separate from the custom
runtime in `firmware/`. Its version is not the version of that custom runtime.

The files live under `hw-revision-unknown/original-fw-version-unknown/` so their
unverified versions remain explicit. Rename those components only when the
hardware revision and original firmware release can be established.

Only this README belongs in Git. Every other file in this directory is ignored:
flash images may contain Wi-Fi credentials and device keys. Keep a private copy
elsewhere; cloning this repository does not restore the backup images.

## Backup contents

- `original-first-4mb.bin`: the first 4 MiB of flash, including the original active
  partition layout. This is a partial backup of the 16 MiB device.
- `original-partitions.bin`: the original partition table, not a complete firmware
  image. It records NVS at `0x9000`, OTA metadata at `0xe000`, application slots
  at `0x10000` and `0x150000`, and SPIFFS at `0x290000`.

SHA-256 checksums, verified after relocating the files:

```text
a170547a56ad2da47997c688fbb2730710d3aa7d4c689f7d701516307309be0a  original-first-4mb.bin
8edc409c4d09a6ac4cb2b3029ad9aaf2edcd2c5e0e89137861b1018a7d21ee15  original-partitions.bin
```

## Restore

From the repository root, using the correct serial port for this device:

```sh
uv run python -m esptool --port /dev/cu.usbserial-01CDD34C --baud 230400 write_flash 0 m5stack-core-basic-firmware/hw-revision-unknown/original-fw-version-unknown/original-first-4mb.bin
```

This uses the ESP32 ROM bootloader and overwrites the current firmware and saved
data in the first 4 MiB. Do not use this device-specific backup for a different
board or assume it covers the remaining 12 MiB of flash.
