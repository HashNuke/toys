Shared M5Stack runtime

Every program uses shared-board-support/common.ini and includes BoardApp.h. Application code
implements appSetup() and appLoop(). BoardApp owns setup()/loop(), servicing
serial firmware updates and authenticated BLE commands before running the app.
The PlatformIO pre-build check rejects programs that omit these entry points.
This applies to our workspace builds; arbitrary external firmware can omit them.

Start a new program by copying m5stack-template to another directory within m5stack/.
Keep appLoop() nonblocking. Use BoardRuntime::takeRefresh() and
BoardRuntime::takeWifiChanged() for application behavior.

Python tools (run from the m5stack directory):
  uv sync
  uv run python -m board_runtime status
  uv run python -m board_runtime wifi_set
  uv run python -m board_runtime wifi_reconnect
  uv run python -m board_runtime refresh
  uv run python -m board_runtime serial_download
  uv run python -m board_runtime reboot

USB serial Wi-Fi setup (no signing key or Bluetooth required):
  uv run python -m board_runtime.serial_wifi
  uv run python -m board_runtime.serial_wifi wifi_reconnect
  uv run python -m board_runtime.serial_wifi status
  Add --port /dev/cu.<port-name> when using another serial port.
  The default command prompts for SSID and a hidden password. Credentials are
  sent directly over the USB serial cable, without echoing or logging them.
  Uses the same connection validation, persistence, and rollback as Bluetooth.

  Raw serial, 115200 baud, one command per newline:
    BOARD:WIFI {"ssid":"network","password":"password","request_id":"0123456789abcdef"}
    BOARD:WIFI_RECONNECT
    BOARD:STATUS
  Wi-Fi JSON request_id is optional; if supplied, use 16 characters.
  Replies: BOARD:RESULT followed by JSON. Syntax errors: BOARD:ERROR.
  Line limit: 512 bytes; oversized lines are discarded completely.
  Responses never include credentials. Only one Wi-Fi command can run at a time.

wifi_set prompts for an SSID and a hidden password. Credentials are encrypted
over Bluetooth, never placed in command-line arguments, and not printed.
The board tests the network before writing credentials to flash; a 30-second
failure restores the previous network. wifi_reconnect tests and resaves the
existing credentials without returning them to the sender.
serial_download pauses the application for 180 seconds; the serial uploader
remains available. Ordinary uploads also work without this command.

One P-256 signing key is shared across authorized sender devices. The board
stores only its public verification key. Private key: ../.devices/sender.pem.
Copy that key privately to another trusted sender along with device.json and
the Python client. Every holder has full command authority; revoking a holder
requires replacing the shared key on all senders and the board. This project
does not automate key rotation. Do not regenerate enrollment files casually.

The board also has a distinct private P-256 encryption identity, stored in NVS
and initially seeded from the ignored shared-board-support/identity/BoardIdentity.h. This
key stays off sender devices; device.json contains only its pinned public key.
The laptop's ../.devices/<board-id>.pem is a private enrollment backup.
These private files and raw flash backups are excluded from Git. This is a
personal-device runtime, not hardware-enforced secure boot or tamper resistance.

Protocol v1:
  BLE service 521cb560-6ce7-4d51-b234-76f821098001
  Read hello  ...8002, write command ...8003, read result ...8004.
  Advertising discovers the board; commands use brief BLE GATT connections.
  hello JSON: version v=1, id (12 lowercase MAC digits), public (65-byte P-256
  uncompressed point in hex), challenge (32 fresh random bytes in hex).
  Verify id and public against the enrolled descriptor before sending anything.

  Request binary layout:
    'BR1\0' | challenge[32] | ephemeral-public[65] | nonce[12] |
    ciphertext-length[2, big endian] | ciphertext + GCM-tag[16] |
    ECDSA-P256-SHA256 signature (DER, <=72 bytes).
  Signature input: 'toys-board-v1' || ASCII device-id || all bytes before signature.
  ECDH: sender ephemeral private key and board pinned encryption public key.
  HKDF-SHA256: salt=challenge, info='toys-board-v1' || ASCII device-id, length=32.
  Request AES-256-GCM AAD: 'toys-board-v1 request' || device-id || challenge.
  Plaintext JSON: request_id (16 hex digits), command, optional command fields.
  wifi_set adds ssid and password. Plaintext limit: 512 bytes.

  Fragment writes: total-length[2, big endian] | offset[2, big endian] | bytes.
  Use writes with response, sequential offsets, at most MTU-7 payload bytes.
  Reassembly is bounded to 768 bytes with a 10-second timeout. Only one command
  is processed at once. The challenge is consumed before executing authenticated
  commands and expires after 120 seconds. Old challenges cannot be replayed.

  Successful authenticated response: nonce[12] | AES-GCM ciphertext | tag[16].
  Response AAD: 'toys-board-v1 response' || device-id || original challenge.
  It includes request_id, result, Wi-Fi connected/IP, serial updater availability,
  and free heap. Credential values are never included. Rejections before
  authentication are plain ERROR messages and should not be treated as trusted
  device responses. The client's encrypted confirmation authenticates the board.

Test:
  uv run python -m pytest -q board_runtime/tests
  uv run pio run -d hacker-news-m5stack -e news
  uv run pio run -d m5stack-template -e template

Applications can register BoardRuntime::setSerialCommandHandler(handler) for
additional newline-terminated serial commands. Reserved update, status, and Wi-Fi
commands are handled by the runtime first. Application handlers must preserve
these services and must not emit secrets. wifi-diagnostics is an example.
