import json
import pytest
from board_runtime.serial_wifi import wifi_line

def test_credentials_with_quotes_backslashes_and_unicode_roundtrip():
    line = wifi_line('Wi-Fi "café"', 'a\\b"cdé123', "abc123")
    assert line.startswith(b"BOARD:WIFI ") and line.endswith(b"\n")
    payload = json.loads(line[len(b"BOARD:WIFI "):])
    assert payload == {"ssid": 'Wi-Fi "café"', "password": 'a\\b"cdé123', "request_id": "abc123"}

@pytest.mark.parametrize("ssid,password", [("", "abcdefgh"), ("é" * 17, "abcdefgh"), ("network", "short"), ("network", "é" * 32), ("net\0work", "abcdefgh"), ("network", "abcd\0efgh")])
def test_invalid_credentials_rejected_before_serial_write(ssid, password):
    with pytest.raises(ValueError): wifi_line(ssid, password, "abc123")

def test_open_network_supported():
    assert json.loads(wifi_line("open-network", "", "abc123")[11:])["password"] == ""
