"""Configure the board's Wi-Fi over USB serial without exposing the password in argv."""
import argparse
import getpass
import json
import secrets
import time
import serial

def wifi_line(ssid, password, request_id):
    if not 1 <= len(ssid.encode()) <= 32 or "\0" in ssid or "\0" in password:
        raise ValueError("SSID must be 1–32 UTF-8 bytes; credentials cannot contain NUL")
    size = len(password.encode())
    if size and not 8 <= size <= 63:
        raise ValueError("Password must be empty or 8–63 UTF-8 bytes")
    payload = json.dumps({"ssid": ssid, "password": password, "request_id": request_id},
                         ensure_ascii=False, separators=(",", ":"))
    line = ("BOARD:WIFI " + payload + "\n").encode()
    if len(line) - 1 > 512:
        raise ValueError("Encoded credentials exceed the serial command limit")
    return line

def execute(port_name, command, ssid=None, password=None):
    request_id = secrets.token_hex(8)
    if command == "wifi_set":
        line = wifi_line(ssid, password, request_id)
    else:
        line = {"wifi_reconnect": b"BOARD:WIFI_RECONNECT\n", "status": b"BOARD:STATUS\n"}[command]
    port = serial.Serial(port=None, baudrate=115200, timeout=1, write_timeout=15, exclusive=True)
    port.dtr = False
    port.rts = False
    port.port = port_name
    port.open()
    try:
        time.sleep(2)
        port.reset_input_buffer()
        port.write(b"HN:PING\n")
        startup_deadline = time.monotonic() + 90
        while time.monotonic() < startup_deadline:
            if port.readline().startswith(b"HN:PONG"):
                break
        else:
            raise TimeoutError("Board's serial command interface did not become ready")
        port.write(line)
        port.flush()
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            response = port.readline().decode("utf-8", errors="replace").strip()
            if response.startswith("BOARD:ERROR"):
                raise RuntimeError(response)
            if response.startswith("BOARD:RESULT "):
                result = json.loads(response[len("BOARD:RESULT "):])
                if command == "wifi_set" and result.get("request_id") != request_id:
                    continue
                return result
        raise TimeoutError("No serial Wi-Fi confirmation received")
    finally:
        port.close()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", default="wifi_set", choices=["wifi_set", "wifi_reconnect", "status"])
    parser.add_argument("--port", default="/dev/cu.usbserial-01CDD34C")
    args = parser.parse_args()
    ssid = password = None
    if args.command == "wifi_set":
        ssid = input("Wi-Fi SSID: ")
        password = getpass.getpass("Wi-Fi password (empty for an open network): ")
    result = execute(args.port, args.command, ssid, password)
    print(json.dumps(result, indent=2))
    if result["result"] != "ok": raise SystemExit(1)

if __name__ == "__main__": main()
