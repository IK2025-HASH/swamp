"""Tests for src/protocol.py — encode/decode round-trips for every message type."""
import json
import struct
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.protocol import (
    encode_message,
    HelloMsg, ChatMsg, FileMetaMsg, FileDataMsg,
    SyncDataMsg, ScreenFrameMsg, AckMsg,
    RoleAnnounceMsg, NodeListMsg, HeartbeatMsg, StateSyncMsg,
    make_hello, make_chat, make_role_announce,
    make_heartbeat, make_node_list, make_state_sync,
    MsgType,
)


def _decode(data: bytes):
    total = struct.unpack(">I", data[:4])[0]
    frame = data[4 : 4 + total]
    try:
        header = json.loads(frame.decode())
        return header, b""
    except (json.JSONDecodeError, UnicodeDecodeError):
        # frame has binary payload — find header_len
        for end in range(2, min(len(frame), 4096)):
            try:
                obj = json.loads(frame[:end].decode())
                if "header_len" in obj:
                    hl = obj["header_len"]
                    return json.loads(frame[:hl].decode()), frame[hl:]
            except Exception:
                continue
        raise ValueError("could not decode frame")


def test_hello():
    h, _ = _decode(make_hello("Alice"))
    assert h["type"] == MsgType.HELLO
    assert h["device_name"] == "Alice"


def test_chat():
    h, _ = _decode(make_chat("Hello world", "Bob", 1234567890.0))
    assert h["type"] == MsgType.CHAT
    assert h["text"] == "Hello world"
    assert h["sender"] == "Bob"
    assert h["timestamp"] == 1234567890.0


def test_file_meta():
    msg = FileMetaMsg(
        filename="photo.jpg", filesize=204800,
        mime_type="image/jpeg", transfer_id="t-001",
    )
    h, _ = _decode(encode_message(msg))
    assert h["type"] == MsgType.FILE_META
    assert h["filename"] == "photo.jpg"
    assert h["filesize"] == 204800
    assert h["transfer_id"] == "t-001"


def test_file_data_with_binary_payload():
    payload = b"\x00\x01\x02\x03" * 256   # 1 KB
    msg = FileDataMsg(
        transfer_id="t-001", chunk_index=0, total_chunks=1, chunk_size=len(payload)
    )
    h, p = _decode(encode_message(msg, payload))
    assert h["type"] == MsgType.FILE_DATA
    assert h["chunk_index"] == 0
    assert h["chunk_size"] == 1024
    assert p == payload


def test_role_announce():
    h, _ = _decode(make_role_announce("master", "ABCD1234", "Alice"))
    assert h["type"] == MsgType.ROLE_ANNOUNCE
    assert h["role"] == "master"
    assert h["node_id"] == "ABCD1234"
    assert h["device_name"] == "Alice"


def test_heartbeat():
    h, _ = _decode(make_heartbeat("N1", 9999.0))
    assert h["type"] == MsgType.HEARTBEAT
    assert h["node_id"] == "N1"
    assert h["timestamp"] == 9999.0


def test_node_list():
    nodes = [
        {"node_id": "A", "name": "Alice", "ip": "10.0.0.1", "port": 54321, "role": "master"},
        {"node_id": "B", "name": "Bob",   "ip": "10.0.0.2", "port": 54321, "role": "node"},
    ]
    h, _ = _decode(make_node_list(nodes))
    assert h["type"] == MsgType.NODE_LIST
    assert len(h["nodes"]) == 2
    assert h["nodes"][0]["name"] == "Alice"


def test_state_sync():
    h, _ = _decode(make_state_sync(
        chat_history=[{"text": "hi", "sender": "Alice", "timestamp": 1.0}],
        files_list=[{"filename": "img.jpg", "size": 500}],
        sync_items=[],
    ))
    assert h["type"] == MsgType.STATE_SYNC
    assert len(h["chat_history"]) == 1
    assert h["chat_history"][0]["text"] == "hi"
    assert len(h["files_list"]) == 1
    assert h["sync_items"] == []


def test_ack():
    msg = AckMsg(ref_type=MsgType.CHAT, ref_id="m-001", status="ok")
    h, _ = _decode(encode_message(msg))
    assert h["type"] == MsgType.ACK
    assert h["status"] == "ok"


def test_sync_data():
    msg = SyncDataMsg(data_type="clipboard", payload="hello clipboard")
    h, _ = _decode(encode_message(msg))
    assert h["type"] == MsgType.SYNC_DATA
    assert h["payload"] == "hello clipboard"


def test_screen_frame_with_jpeg():
    jpeg = b"\xff\xd8\xff" + b"\x00" * 100   # fake JPEG header
    msg = ScreenFrameMsg(
        frame_index=3, width=640, height=480, chunk_size=len(jpeg)
    )
    h, p = _decode(encode_message(msg, jpeg))
    assert h["type"] == MsgType.SCREEN_FRAME
    assert h["frame_index"] == 3
    assert p == jpeg


if __name__ == "__main__":
    import unittest
    # Run all test_* functions manually
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
