M5Stack Core Wi-Fi diagnostics

Run commands from the m5stack/ directory.

Build: uv run pio run -d wifi-diagnostics
Install using the existing serial updater:
uv run python hacker-news-m5stack/upload_serial.py wifi-diagnostics/.pio/build/diagnostics/firmware.bin

The laptop stays on its existing Wi-Fi. All probes run on the ESP32.
uv run python -m board_runtime.diagnostics wifi YOUR_SSID
(password is prompted privately)
uv run python -m board_runtime.diagnostics status
uv run python -m board_runtime.diagnostics scan
uv run python -m board_runtime.diagnostics probe
uv run python -m board_runtime.diagnostics fetch http://192.168.0.1/ --output /tmp/router.html

Raw commands, newline terminated at 115200 baud:
DIAG:STATUS
DIAG:SCAN
DIAG:PROBE
DIAG:FETCH http://address/path
DIAG:MONITOR 30 (seconds, minimum 30; 0 disables)
DIAG:POWERSAVE OFF / DIAG:POWERSAVE ON
DIAG:DHCP (restore automatic addressing)
DIAG:STATIC {"ip":"192.168.0.247","gateway":"192.168.0.1","mask":"255.255.255.0"}
DIAG:REQUEST {"url":"http://192.168.0.1/","method":"GET","headers":{},"body":""}

Every 10 seconds, passive status includes RSSI, BSSID/channel, DHCP network
configuration, disconnect count/reason. Active monitoring is OFF at boot so idle
failures can be reproduced. PROBE tests gateway/external ICMP, external TCP,
uncached UDP DNS against DHCP and public resolvers, and two HTTP connectivity
checks. ICMP can be filtered; TCP/DNS/HTTP provide independent evidence.
FETCH relays an HTTP GET over USB, with status/headers and base64 body chunks,
limited to 64 KiB. HTTP only; do not use it to send credentials over the internet.
SCAN is an explicit active scan and may briefly interrupt normal radio traffic.

Recovery/update, signed BLE, and transactional serial Wi-Fi configuration remain
available through BoardRuntime. Command execution may occupy up to ~30 seconds
for a probe; recovery resumes between probes. Default Wi-Fi power save is kept.
The ESP32 supports only 2.4 GHz; it cannot directly test a 5 GHz client connection.

Use Diagnostics as a Python context with one open serial connection for long
experiments; opening a USB serial connection can reset some boards. Private
router responses and captures belong in ignored ../.devices/, not in Git.

Persistent serial bridge:
uv run python -m board_runtime.diagnostic_bridge
It serves JSON RPC on 127.0.0.1:8766 and continuously drains serial status output.
Use Authorization: Bearer <token from ../.devices/diagnostics/bridge.token>.
POST {"command":"DIAG:PROBE"}, {"action":"idle","seconds":120}, or
{"action":"http","url":"http://192.168.0.1/"}. The HTTP action also accepts
method, headers, and body, and returns the response body in base64.
{"action":"wifi","ssid":"...","password":"..."} stages credentials using
BoardRuntime and samples association/IP state during the transaction.
HTTP requests fit within the existing 512-byte serial command limit. POST can
change router settings, so use read operations until a specific fix is chosen.
Static addressing changes only the ESP32 and is temporary until reboot; return
to DHCP before internet testing. A static management address alone does not
test whether normal clients can obtain leases or reach the internet.
