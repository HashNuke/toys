"""Hardware checks. Temporarily tests an unavailable Wi-Fi network and restores it."""
import asyncio
import json
import secrets
import struct
import time
from pathlib import Path
from bleak import BleakClient, BleakScanner
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from .protocol import SERVICE, HELLO, COMMAND, RESULT, make_request, read_response

ROOT = Path(__file__).resolve().parents[2]

async def check():
    descriptor = json.loads((ROOT / ".devices/device.json").read_text())
    signing = serialization.load_pem_private_key((ROOT / ".devices/sender.pem").read_bytes(), None)
    board = await BleakScanner.find_device_by_filter(
        lambda d, a: a.local_name == "Toys-" + descriptor["id"][-6:] and SERVICE in a.service_uuids, timeout=15)
    if not board: raise RuntimeError("Board not discovered")
    async with BleakClient(board) as client:
        async def hello(): return json.loads(bytes(await client.read_gatt_char(HELLO)))
        async def exchange(packet, key, greeting, request_id, error=None):
            size = min(176, max(16, client.mtu_size - 7))
            for offset in range(0, len(packet), size):
                await client.write_gatt_char(COMMAND, struct.pack(">HH", len(packet), offset) + packet[offset:offset+size], response=True)
            deadline = time.monotonic() + 65
            while time.monotonic() < deadline:
                raw = bytes(await client.read_gatt_char(RESULT))
                if raw.startswith(b"ERROR:"):
                    if error and error in raw.decode(): return
                    raise RuntimeError(raw.decode())
                if raw:
                    response = read_response(raw, key, greeting["id"], bytes.fromhex(greeting["challenge"]))
                    if response["request_id"] == request_id:
                        if error: raise AssertionError("Unauthenticated request was accepted")
                        return response
                await asyncio.sleep(.2)
            raise TimeoutError("Command timed out")
        async def send(command, **fields):
            greeting = await hello()
            packet, key, request_id = make_request(signing, descriptor, greeting, command, **fields)
            return await exchange(packet, key, greeting, request_id)

        greeting = await hello()
        packet, key, request_id = make_request(signing, descriptor, greeting, "status")
        tampered = bytearray(packet); tampered[120] ^= 1
        await exchange(bytes(tampered), key, greeting, request_id, "signature invalid")
        print("PASS: tampered command rejected", flush=True)
        rogue = ec.generate_private_key(ec.SECP256R1())
        unauthorized, rogue_key, rogue_id = make_request(rogue, descriptor, greeting, "status")
        await exchange(unauthorized, rogue_key, greeting, rogue_id, "signature invalid")
        print("PASS: unauthorized signing key rejected", flush=True)
        status = await exchange(packet, key, greeting, request_id)
        assert status["result"] == "ok" and status["serial_update"]
        print(f"PASS: authenticated status, heap={status['free_heap']}", flush=True)
        await exchange(packet, key, greeting, request_id, "stale")
        print("PASS: replay rejected", flush=True)
        reconnect = await send("wifi_reconnect")
        assert reconnect["result"] == "ok" and reconnect["wifi_connected"]
        print("PASS: Wi-Fi credentials tested and persisted via BLE", flush=True)
        failed = await send("wifi_set", ssid="TOYS-NO-NETWORK-" + secrets.token_hex(4), password="temporary-test-only")
        assert failed["result"] == "error" and "restored" in failed["error"]
        for _ in range(20):
            await asyncio.sleep(.5)
            status = await send("status")
            if status["wifi_connected"]: break
        assert status["wifi_connected"]
        print("PASS: invalid Wi-Fi credentials rolled back and original network reconnected", flush=True)
        assert (await send("refresh"))["result"] == "ok"
        print("PASS: signed refresh accepted", flush=True)
        assert (await send("serial_download"))["result"] == "ok"
        print("PASS: signed software-download command accepted", flush=True)
        assert (await send("reboot"))["result"] == "ok"
        print("PASS: signed reboot accepted; board will resume news app", flush=True)

if __name__ == "__main__": asyncio.run(check())
