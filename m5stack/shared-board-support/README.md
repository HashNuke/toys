# Shared board support

Custom support code and build configuration shared by this repository's M5Stack
apps. This is project-written source, separate from the original device firmware
images documented in `../m5stack-core-basic-firmware/`.

- `lib/BoardRuntime/`: board startup, software serial updates, signed and encrypted
  Bluetooth commands, and USB/Bluetooth Wi-Fi configuration with connection tests
  and rollback.
- `common.ini`: shared PlatformIO settings and dependencies.
- `partitions.csv`: the OTA partition layout used by every app.
- `check_runtime.py`: build checks requiring apps to use `BoardApp.h` and implement
  `appSetup()` and `appLoop()`.
- `identity/BoardIdentity.h`: ignored local device identity containing a private
  key. Keep the existing identity private; do not commit or regenerate it.

Apps inherit `../shared-board-support/common.ini` in their `platformio.ini`.
This directory is support for those apps, not a standalone firmware application.
