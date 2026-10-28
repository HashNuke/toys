import json
import secrets
import struct
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SERVICE = "521cb560-6ce7-4d51-b234-76f821098001"
HELLO = "521cb560-6ce7-4d51-b234-76f821098002"
COMMAND = "521cb560-6ce7-4d51-b234-76f821098003"
RESULT = "521cb560-6ce7-4d51-b234-76f821098004"
DOMAIN = b"toys-board-v1"
PREFIX = b"BR1\x00"

def public_bytes(key):
    return key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)

def derive_key(private, public, challenge, device_id):
    secret = private.exchange(ec.ECDH(), public)
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=challenge,
                info=DOMAIN + device_id.encode()).derive(secret)

def aad(device_id, challenge, response=False):
    return DOMAIN + (b" response" if response else b" request") + device_id.encode() + challenge

def make_request(signing_key, descriptor, hello, command, **arguments):
    if hello["v"] != 1 or hello["id"] != descriptor["id"] or hello["public"] != descriptor["public"]:
        raise ValueError("Device identity does not match the enrolled board")
    device_id = hello["id"]
    challenge = bytes.fromhex(hello["challenge"])
    if len(challenge) != 32:
        raise ValueError("Invalid challenge")
    peer = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), bytes.fromhex(hello["public"]))
    ephemeral = ec.generate_private_key(ec.SECP256R1())
    key = derive_key(ephemeral, peer, challenge, device_id)
    request_id = secrets.token_hex(8)
    body = json.dumps({"request_id": request_id, "command": command, **arguments}, separators=(",", ":")).encode()
    if len(body) > 512:
        raise ValueError("Command exceeds 512 bytes")
    nonce = secrets.token_bytes(12)
    cipher = AESGCM(key).encrypt(nonce, body, aad(device_id, challenge))
    unsigned = PREFIX + challenge + public_bytes(ephemeral.public_key()) + nonce + struct.pack(">H", len(cipher)) + cipher
    signature = signing_key.sign(DOMAIN + device_id.encode() + unsigned, ec.ECDSA(hashes.SHA256()))
    return unsigned + signature, key, request_id

def read_request(packet, signing_public, device_private, device_id, challenge):
    """Reference decoder used by protocol tests; firmware implements the same format."""
    if len(packet) < 131 or packet[:4] != PREFIX or packet[4:36] != challenge:
        raise ValueError("Invalid or stale envelope")
    length = struct.unpack(">H", packet[113:115])[0]
    end = 115 + length
    if length < 16 or length > 528 or not end < len(packet) <= end + 72:
        raise ValueError("Invalid envelope length")
    signing_public.verify(packet[end:], DOMAIN + device_id.encode() + packet[:end], ec.ECDSA(hashes.SHA256()))
    peer = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), packet[36:101])
    key = derive_key(device_private, peer, challenge, device_id)
    plain = AESGCM(key).decrypt(packet[101:113], packet[115:end], aad(device_id, challenge))
    return json.loads(plain), key

def read_response(packet, key, device_id, challenge):
    return json.loads(AESGCM(key).decrypt(packet[:12], packet[12:], aad(device_id, challenge, True)))
