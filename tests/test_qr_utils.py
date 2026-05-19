"""Tests for src/utils/qr_utils.py."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.utils.qr_utils import (
    generate_qr_payload,
    parse_qr_payload,
    generate_qr_image,
    get_local_ip,
    QRCODE_AVAILABLE,
    PIL_AVAILABLE,
)


def test_payload_round_trip():
    p = generate_qr_payload("Alice", "192.168.1.5", 54321, "master", "ABCD1234")
    info = parse_qr_payload(p)
    assert info["name"] == "Alice"
    assert info["ip"] == "192.168.1.5"
    assert info["port"] == 54321
    assert info["role"] == "master"
    assert info["node_id"] == "ABCD1234"


def test_payload_is_compact_json():
    p = generate_qr_payload("X", "1.2.3.4", 54321, "node", "N1")
    import json
    obj = json.loads(p)
    assert set(obj.keys()) == {"n", "ip", "p", "r", "id"}


def test_parse_bad_payload_returns_none():
    assert parse_qr_payload("{not valid}") is None
    assert parse_qr_payload("") is None
    assert parse_qr_payload("null") is None


def test_parse_missing_fields_returns_none():
    import json
    # Missing required field "n"
    bad = json.dumps({"ip": "1.2.3.4", "p": 54321, "r": "node", "id": "X"})
    assert parse_qr_payload(bad) is None


def test_port_coerced_to_int():
    import json
    payload = json.dumps({"n": "A", "ip": "1.2.3.4", "p": "54321", "r": "node", "id": "X"})
    info = parse_qr_payload(payload)
    assert isinstance(info["port"], int)


def test_get_local_ip_returns_string():
    ip = get_local_ip()
    assert isinstance(ip, str)
    assert len(ip) >= 7   # shortest valid IP is "1.2.3.4"
    assert "." in ip


def test_generate_qr_image():
    if not QRCODE_AVAILABLE or not PIL_AVAILABLE:
        print("    (skipped — qrcode/PIL not available)")
        return
    payload = generate_qr_payload("Bob", "10.0.0.1", 54321, "node", "N2")
    img = generate_qr_image(payload, size=200)
    assert img is not None
    assert img.size == (200, 200)
    assert img.mode == "RGBA"


def test_generate_qr_image_default_size():
    if not QRCODE_AVAILABLE or not PIL_AVAILABLE:
        return
    payload = generate_qr_payload("A", "1.1.1.1", 54321, "node", "X")
    img = generate_qr_image(payload)
    assert img.size == (300, 300)


if __name__ == "__main__":
    g = globals()
    tests = [v for k, v in g.items() if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  ✓  {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ✗  {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed  {failed} failed")
    sys.exit(failed)
