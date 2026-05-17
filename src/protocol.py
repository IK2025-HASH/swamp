"""
protocol.py — Swamp message framing and message types.

Frame format:
  [4 bytes big-endian: total frame length]
  [N bytes: JSON header (UTF-8)]
  [0 or more bytes: binary payload]

The JSON header always contains at least:
  {"type": "<MSG_TYPE>", "header_len": <N>, ...}

Binary payload (if any) follows immediately after the JSON header bytes.
Total frame length = len(json_header_bytes) + len(binary_payload).
"""

import json
import struct
import asyncio
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Dict, Any


# ---------------------------------------------------------------------------
# Message type constants
# ---------------------------------------------------------------------------

class MsgType(str, Enum):
    HELLO         = "HELLO"          # Announce device name/version on connect
    CHAT          = "CHAT"           # Text chat message
    FILE_META     = "FILE_META"      # File transfer metadata (name, size, mime)
    FILE_DATA     = "FILE_DATA"      # Binary file chunk / screen frame
    SYNC_DATA     = "SYNC_DATA"      # Contacts JSON or clipboard text
    SCREEN_FRAME  = "SCREEN_FRAME"   # Compressed JPEG screen frame
    ACK           = "ACK"            # Generic acknowledgement
    # ── topology messages ─────────────────────────────────────────────
    ROLE_ANNOUNCE = "ROLE_ANNOUNCE"  # Device broadcasts its role + node_id
    NODE_LIST     = "NODE_LIST"      # Master sends full peer list to new node
    RELAY         = "RELAY"          # Master relays a frame between nodes
    HEARTBEAT     = "HEARTBEAT"      # Node → master keepalive
    STATE_SYNC    = "STATE_SYNC"     # Master sends shared state to new node
    BROADCAST     = "BROADCAST"      # Master re-broadcasts a node's msg to all


# ---------------------------------------------------------------------------
# Dataclasses for each message type
# ---------------------------------------------------------------------------

@dataclass
class HelloMsg:
    device_name: str
    version: str = "1.0"
    type: str = MsgType.HELLO


@dataclass
class ChatMsg:
    text: str
    sender: str
    timestamp: float
    type: str = MsgType.CHAT


@dataclass
class FileMetaMsg:
    filename: str
    filesize: int
    mime_type: str
    transfer_id: str
    type: str = MsgType.FILE_META


@dataclass
class FileDataMsg:
    transfer_id: str
    chunk_index: int
    total_chunks: int
    chunk_size: int          # size of binary payload in bytes
    type: str = MsgType.FILE_DATA


@dataclass
class SyncDataMsg:
    data_type: str           # "contacts" | "clipboard"
    payload: str             # JSON string for contacts, plain text for clipboard
    type: str = MsgType.SYNC_DATA


@dataclass
class ScreenFrameMsg:
    frame_index: int
    width: int
    height: int
    chunk_size: int          # size of JPEG bytes that follow
    type: str = MsgType.SCREEN_FRAME


@dataclass
class RoleAnnounceMsg:
    role: str        # "master" | "node"
    node_id: str
    device_name: str
    type: str = MsgType.ROLE_ANNOUNCE


@dataclass
class NodeListMsg:
    nodes: list      # [{node_id, name, ip, port, role}, ...]
    type: str = MsgType.NODE_LIST


@dataclass
class RelayMsg:
    from_node_id: str
    to_node_id: str   # "" = broadcast to every connected node
    inner_type: str   # MsgType of the wrapped message
    inner_data: str   # base64-encoded inner frame
    type: str = MsgType.RELAY


@dataclass
class HeartbeatMsg:
    node_id: str
    timestamp: float
    type: str = MsgType.HEARTBEAT


@dataclass
class StateSyncMsg:
    chat_history: list   # [{text, sender, timestamp}, ...]
    files_list: list     # [{filename, size, sender, timestamp}, ...]
    sync_items: list     # [{data_type, payload, timestamp}, ...]
    type: str = MsgType.STATE_SYNC


@dataclass
class AckMsg:
    ref_type: str            # type of message being ACK'd
    ref_id: str              # transfer_id or message identifier
    status: str = "ok"       # "ok" | "error"
    message: str = ""
    type: str = MsgType.ACK


# ---------------------------------------------------------------------------
# Frame encode / decode
# ---------------------------------------------------------------------------

def encode_frame(header: Dict[str, Any], payload: bytes = b"") -> bytes:
    """Encode a single frame: 4-byte length prefix + JSON header + binary payload."""
    header_bytes = json.dumps(header).encode("utf-8")
    # Store header length inside the header so decoder knows where JSON ends
    # We rebuild with the header_len field inserted
    header["header_len"] = len(header_bytes)
    header_bytes = json.dumps(header).encode("utf-8")
    # Recalculate in case the extra field changed length (converge in 2 passes)
    header["header_len"] = len(header_bytes)
    header_bytes = json.dumps(header).encode("utf-8")
    header["header_len"] = len(header_bytes)
    header_bytes = json.dumps(header).encode("utf-8")

    total_len = len(header_bytes) + len(payload)
    length_prefix = struct.pack(">I", total_len)
    return length_prefix + header_bytes + payload


def encode_message(msg_dataclass, payload: bytes = b"") -> bytes:
    """Encode a dataclass message instance into a wire frame."""
    header = asdict(msg_dataclass) if hasattr(msg_dataclass, "__dataclass_fields__") else dict(msg_dataclass)
    return encode_frame(header, payload)


async def read_frame(reader: asyncio.StreamReader):
    """
    Read exactly one frame from an asyncio StreamReader.

    Returns (header_dict, payload_bytes) or raises EOFError/ConnectionResetError.
    """
    length_data = await reader.readexactly(4)
    total_len = struct.unpack(">I", length_data)[0]

    if total_len == 0:
        return {}, b""

    if total_len > 256 * 1024 * 1024:  # 256 MB sanity cap
        raise ValueError(f"Frame too large: {total_len} bytes")

    frame_data = await reader.readexactly(total_len)

    # Extract header: read header_len from the start
    # We need to parse a prefix of the JSON to find header_len.
    # Strategy: decode the whole thing, find the header_len field.
    # Since header_len is always present, do a two-pass approach:
    # First, try to decode as much JSON as needed.
    # For simplicity we scan for "header_len" in the first 64 bytes.
    try:
        # Attempt to parse header by finding the header_len value quickly
        preview = frame_data[:256].decode("utf-8", errors="replace")
        # Quick heuristic: parse the JSON up to a closing brace that gives us header_len
        # Reliable approach: try increasing slices until valid JSON with header_len
        # In practice, header_len is known after the full JSON is parsed,
        # but we stored it inside the JSON. We use the following trick:
        # Parse the entire frame as JSON first (it might be all header, no payload).
        try:
            header = json.loads(frame_data.decode("utf-8"))
            payload = b""
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Frame has binary payload; use header_len field
            # Find header_len by scanning the JSON preamble
            header_len = _extract_header_len(frame_data)
            header_bytes = frame_data[:header_len]
            payload = frame_data[header_len:]
            header = json.loads(header_bytes.decode("utf-8"))
    except Exception as e:
        raise ValueError(f"Failed to decode frame: {e}") from e

    return header, payload


def _extract_header_len(frame_data: bytes) -> int:
    """
    Extract the header_len value from a frame that contains binary payload.
    We parse up to the first closing brace that yields valid JSON.
    """
    # Scan forward for a valid JSON object containing header_len
    for end in range(2, min(len(frame_data), 4096)):
        chunk = frame_data[:end]
        try:
            obj = json.loads(chunk.decode("utf-8"))
            if "header_len" in obj:
                return obj["header_len"]
        except Exception:
            continue
    raise ValueError("Could not determine header_len from frame")


# ---------------------------------------------------------------------------
# Higher-level helpers
# ---------------------------------------------------------------------------

def make_hello(device_name: str) -> bytes:
    return encode_message(HelloMsg(device_name=device_name))


def make_chat(text: str, sender: str, timestamp: float) -> bytes:
    return encode_message(ChatMsg(text=text, sender=sender, timestamp=timestamp))


def make_ack(ref_type: str, ref_id: str, status: str = "ok", message: str = "") -> bytes:
    return encode_message(AckMsg(ref_type=ref_type, ref_id=ref_id, status=status, message=message))


def make_role_announce(role: str, node_id: str, device_name: str) -> bytes:
    return encode_message(RoleAnnounceMsg(role=role, node_id=node_id, device_name=device_name))


def make_heartbeat(node_id: str, timestamp: float) -> bytes:
    return encode_message(HeartbeatMsg(node_id=node_id, timestamp=timestamp))


def make_node_list(nodes: list) -> bytes:
    return encode_message(NodeListMsg(nodes=nodes))


def make_state_sync(chat_history: list, files_list: list, sync_items: list) -> bytes:
    return encode_message(StateSyncMsg(
        chat_history=chat_history,
        files_list=files_list,
        sync_items=sync_items,
    ))
