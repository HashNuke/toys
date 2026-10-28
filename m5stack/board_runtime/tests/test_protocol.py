import json
import os
import pytest
from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from board_runtime.protocol import *

@pytest.fixture
def identity():
    sender = ec.generate_private_key(ec.SECP256R1())
    device = ec.generate_private_key(ec.SECP256R1())
    descriptor = {"v": 1, "id": "240ac45b5a4c", "public": public_bytes(device.public_key()).hex()}
    hello = {**descriptor, "challenge": os.urandom(32).hex()}
    return sender, device, descriptor, hello

def test_wifi_roundtrip_and_encrypted_confirmation(identity):
    sender, device, descriptor, hello = identity
    packet, key, request_id = make_request(sender, descriptor, hello, "wifi_set", ssid="private-network", password="super-secret")
    assert b"super-secret" not in packet and b"private-network" not in packet
    command, device_key = read_request(packet, sender.public_key(), device, hello["id"], bytes.fromhex(hello["challenge"]))
    assert command["password"] == "super-secret" and device_key == key
    nonce = os.urandom(12)
    response = nonce + AESGCM(key).encrypt(nonce, json.dumps({"request_id": request_id, "result": "ok"}).encode(), aad(hello["id"], bytes.fromhex(hello["challenge"]), True))
    assert read_response(response, key, hello["id"], bytes.fromhex(hello["challenge"]))["result"] == "ok"

def test_tampering_rejected(identity):
    sender, device, descriptor, hello = identity
    packet, _, _ = make_request(sender, descriptor, hello, "status")
    changed = bytearray(packet); changed[120] ^= 1
    with pytest.raises(InvalidSignature):
        read_request(bytes(changed), sender.public_key(), device, hello["id"], bytes.fromhex(hello["challenge"]))

def test_untrusted_sender_rejected(identity):
    sender, device, descriptor, hello = identity
    rogue = ec.generate_private_key(ec.SECP256R1())
    packet, _, _ = make_request(rogue, descriptor, hello, "status")
    with pytest.raises(InvalidSignature):
        read_request(packet, sender.public_key(), device, hello["id"], bytes.fromhex(hello["challenge"]))

def test_replay_with_new_challenge_rejected(identity):
    sender, device, descriptor, hello = identity
    packet, _, _ = make_request(sender, descriptor, hello, "status")
    with pytest.raises(ValueError):
        read_request(packet, sender.public_key(), device, hello["id"], os.urandom(32))

def test_identity_substitution_rejected(identity):
    sender, _, descriptor, hello = identity
    with pytest.raises(ValueError): make_request(sender, descriptor, {**hello, "id": "000000000000"}, "status")
    with pytest.raises(ValueError): make_request(sender, descriptor, {**hello, "public": "00"}, "status")

def test_wrong_target_and_modified_response_rejected(identity):
    sender, device, descriptor, hello = identity
    packet, key, _ = make_request(sender, descriptor, hello, "status")
    with pytest.raises(InvalidSignature):
        read_request(packet, sender.public_key(), device, "000000000000", bytes.fromhex(hello["challenge"]))
    nonce = os.urandom(12)
    response = nonce + AESGCM(key).encrypt(nonce, b'{}', aad(hello["id"], bytes.fromhex(hello["challenge"]), True))
    with pytest.raises(InvalidTag): read_response(response[:-1] + bytes([response[-1] ^ 1]), key, hello["id"], bytes.fromhex(hello["challenge"]))
