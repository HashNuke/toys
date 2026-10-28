import argparse
import asyncio
import getpass
import json
import os
import secrets
import struct
import time
from pathlib import Path
from bleak import BleakClient, BleakScanner
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from .protocol import SERVICE, HELLO, COMMAND, RESULT, make_request, public_bytes, read_response

ROOT = Path(__file__).resolve().parents[2]
PRIVATE = ROOT / ".devices"
IDENTITY = ROOT / "m5stack/firmware/identity/BoardIdentity.h"

def save_private(path, contents):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(contents)

def initialize(device_id):
    device_id = device_id.replace(":", "").lower()
    if len(device_id) != 12 or any(c not in "0123456789abcdef" for c in device_id):
        raise ValueError("Expected the board's 12-digit MAC address")
    key_path = PRIVATE / "sender.pem"
    if not key_path.exists():
        key = ec.generate_private_key(ec.SECP256R1())
        save_private(key_path, key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                              serialization.NoEncryption()))
    signing = serialization.load_pem_private_key(key_path.read_bytes(), None)
    device_path = PRIVATE / f"{device_id}.pem"
    if device_path.exists():
        device = serialization.load_pem_private_key(device_path.read_bytes(), None)
    else:
        device = ec.generate_private_key(ec.SECP256R1())
        save_private(device_path, device.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                     serialization.NoEncryption()))
    descriptor = {"v": 1, "id": device_id, "public": public_bytes(device.public_key()).hex()}
    (PRIVATE / "device.json").write_text(json.dumps(descriptor, indent=2) + "\n")
    values = {
        "DEVICE_PRIVATE": device.private_numbers().private_value.to_bytes(32, "big"),
        "DEVICE_PUBLIC": public_bytes(device.public_key()),
        "SENDER_PUBLIC": public_bytes(signing.public_key()),
    }
    header = '#pragma once\n#include <stdint.h>\n'
    header += f'static const char BOARD_DEVICE_ID[] = "{device_id}";\n'
    for name, value in values.items():
        header += f'static const uint8_t BOARD_{name}[] = {{' + ','.join(f'0x{b:02x}' for b in value) + '};\n'
    IDENTITY.parent.mkdir(parents=True, exist_ok=True)
    IDENTITY.write_text(header)
    IDENTITY.chmod(0o600)
    print(f"Board {device_id} enrolled; shared sender key saved privately in ../.devices/sender.pem")

async def send(args):
    descriptor = json.loads(args.device.read_text())
    signing = serialization.load_pem_private_key(args.key.read_bytes(), None)
    arguments = {}
    if args.command == "wifi_set":
        ssid = input("Wi-Fi SSID: ")
        password = getpass.getpass("Wi-Fi password (empty for an open network): ")
        if not 1 <= len(ssid.encode()) <= 32 or '\0' in ssid or '\0' in password:
            raise ValueError("SSID must be 1–32 UTF-8 bytes and contain no NUL")
        size = len(password.encode())
        if size and not 8 <= size <= 63:
            raise ValueError("Password must be empty or 8–63 UTF-8 bytes")
        arguments = {"ssid": ssid, "password": password}
    print("Discovering the board over Bluetooth...", flush=True)
    def match(device, advert):
        return SERVICE in [uuid.lower() for uuid in advert.service_uuids] and (
            advert.local_name == "Toys-" + descriptor["id"][-6:])
    board = await BleakScanner.find_device_by_filter(match, timeout=15)
    if not board:
        raise RuntimeError("Board not found; keep it powered and within Bluetooth range")
    async with BleakClient(board, timeout=20) as client:
        hello = json.loads(bytes(await client.read_gatt_char(HELLO)))
        packet, key, request_id = make_request(signing, descriptor, hello, args.command, **arguments)
        chunk_size = min(176, max(16, client.mtu_size - 7))
        for offset in range(0, len(packet), chunk_size):
            await client.write_gatt_char(COMMAND, struct.pack(">HH", len(packet), offset) + packet[offset:offset+chunk_size], response=True)
        deadline = time.monotonic() + 65
        while time.monotonic() < deadline:
            raw = bytes(await client.read_gatt_char(RESULT))
            if raw.startswith(b"ERROR:"):
                raise RuntimeError(raw.decode())
            if raw:
                response = read_response(raw, key, hello["id"], bytes.fromhex(hello["challenge"]))
                if response.get("request_id") == request_id:
                    print(json.dumps(response, indent=2))
                    if response.get("result") == "error": raise RuntimeError(response["error"])
                    return response
            await asyncio.sleep(.3)
        raise TimeoutError("No command confirmation received")

parser = argparse.ArgumentParser(description="Signed and encrypted commands for the M5Stack")
parser.add_argument("command", choices=["init", "status", "wifi_set", "wifi_reconnect", "refresh", "serial_download", "reboot"])
parser.add_argument("--mac", default="240ac45b5a4c", help="Board MAC for first enrollment")
parser.add_argument("--device", type=Path, default=PRIVATE / "device.json")
parser.add_argument("--key", type=Path, default=PRIVATE / "sender.pem")
args = parser.parse_args()
if args.command == "init": initialize(args.mac)
else: asyncio.run(send(args))
