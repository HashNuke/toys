"""Verify USB serial provisioning, including recovery from invalid credentials."""
import secrets
from .serial_wifi import execute

def main():
    port = "/dev/cu.usbserial-01CDD34C"
    result = execute(port, "status")
    assert result["result"] == "ok" and result["serial_update"]
    print("PASS: serial status and updater available", flush=True)
    result = execute(port, "wifi_reconnect")
    assert result["result"] == "ok" and result["wifi_connected"]
    print("PASS: credentials validated and saved over serial", flush=True)
    result = execute(port, "wifi_set", "TOYS-NO-NETWORK-" + secrets.token_hex(4), "temporary-test-only")
    assert result["result"] == "error" and "restored" in result["error"]
    print("PASS: unavailable Wi-Fi rejected and previous credentials restored", flush=True)
    result = execute(port, "status")
    assert result["result"] == "ok" and result["wifi_connected"]
    print("PASS: original Wi-Fi reconnects after reboot; credentials were preserved", flush=True)

if __name__ == "__main__": main()
