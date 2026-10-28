#!/usr/bin/env python3
"""Upload an application through the installed serial-update firmware."""
import argparse
import hashlib
import time
from pathlib import Path
import serial

parser = argparse.ArgumentParser()
parser.add_argument("firmware", type=Path)
parser.add_argument("--port", default="/dev/cu.usbserial-01CDD34C")
args = parser.parse_args()
firmware = args.firmware.read_bytes()
if not 0 < len(firmware) <= 0x1b0000:
    raise SystemExit("Firmware doesn't fit the application partition")
port = serial.Serial(port=None, baudrate=115200, timeout=1, write_timeout=15)
port.dtr = False
port.rts = False
port.port = args.port
port.open()

def wait_for(prefix, seconds=90):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        line = port.readline().decode("utf-8", errors="replace").strip()
        if line.startswith("HN:ERROR"):
            raise RuntimeError(line)
        if line.startswith(prefix):
            return line
    raise TimeoutError(f"Device didn't respond with {prefix}")

try:
    time.sleep(2)
    port.reset_input_buffer()
    port.write(b"HN:PING\n")
    print(wait_for("HN:PONG"), flush=True)
    digest = hashlib.md5(firmware).hexdigest()
    port.write(f"HN:UPDATE {len(firmware)} {digest}\n".encode())
    wait_for("HN:READY")
    print(f"Sending {len(firmware):,} bytes", flush=True)
    for offset in range(0, len(firmware), 1024):
        chunk = firmware[offset:offset + 1024]
        port.write(chunk)
        port.flush()
        ack = wait_for("HN:ACK ", 20)
        if ack != f"HN:ACK {offset + len(chunk)}":
            raise RuntimeError(f"Unexpected acknowledgement: {ack}")
        if offset % (1024 * 100) == 0:
            print(f"{100 * (offset + len(chunk)) // len(firmware)}%", flush=True)
    print(wait_for("HN:DONE", 20), flush=True)
finally:
    port.close()
