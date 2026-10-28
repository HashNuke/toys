# Private M5Stack flash backups

This directory holds local recovery backups taken before installing this
project's firmware. These are snapshots from the device, separate from the
custom source code in `firmware/`.

Only this README belongs in Git. Backup contents are ignored because flash
images may contain saved Wi-Fi passwords, device keys, and other private data.
Keep a private copy elsewhere if recovery matters; cloning this repository
does not restore these files.

The local backups are:

- `original-first-4mb.bin`: the first 4 MiB of the original flash, including its
  active partition layout. The device has 16 MiB of flash; this is a partial
  device backup.
- `original-partitions.bin`: the original partition-table backup, useful for
  inspecting the old layout. It is not a complete firmware image.

To restore the original first 4 MiB, run from the repository root:

```sh
uv run esptool --port /dev/cu.usbserial-01CDD34C --baud 230400 write_flash 0 firmware-backups/original-first-4mb.bin
```

Use the correct serial port for your machine. This uses the ESP32 ROM
bootloader and overwrites the current firmware and saved data in that region.
