For every firmware program built for M5Stack:
- Use m5stack/shared-board-support/lib/BoardRuntime and its BoardApp.h entry points.
- Implement appSetup() and appLoop(); do not replace setup()/loop().
- Preserve the OTA partition layout and the serial update protocol.
- Preserve signed, encrypted BLE commands and Wi-Fi credential refresh.
- Preserve USB serial Wi-Fi configuration (BOARD:WIFI) and its connection test/rollback.
- Never commit .devices, BoardIdentity.h, credentials, or flash backups.
- Build with uv run pio and test protocol changes with uv run python -m pytest.
- Run a software serial update and verify the app boots after firmware changes.
Do not change the existing device identity or shared sender signing key unless
the user explicitly requests key rotation. All sender devices share sender.pem.
