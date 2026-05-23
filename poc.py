#!/usr/bin/env python3
"""
poc.py — Swamp Proof of Concept (headless, no display needed)

Simulates a Master + two Nodes exchanging messages on localhost.
Proves the full stack:
  ✓ TCP connect + HELLO exchange
  ✓ ROLE_ANNOUNCE (master / node)
  ✓ STATE_SYNC on join
  ✓ Chat delivery + master broadcast relay
  ✓ File transfer (chunked, integrity check)
  ✓ Node-to-node direct message via master relay

Run:  python3 poc.py
"""

import asyncio
import hashlib
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(__file__))

from src.network.server import SwampServer
from src.network.client import SwampClient
from src.protocol import (
    make_chat, make_role_announce, make_state_sync, make_node_list,
    MsgType, encode_message, SyncDataMsg,
)
from src.network.topology import SwampTopology, NodeRole, PeerInfo

# ── Ports ─────────────────────────────────────────────────────────────────────
MASTER_PORT = 54380
NODE_A_PORT = 54381   # Node A also runs a server (for direct connections)

# ── Terminal colours ───────────────────────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
AMBER  = "\033[93m"   # master
BLUE   = "\033[94m"   # node
GREEN  = "\033[92m"   # success
DIM    = "\033[90m"   # dim
RED    = "\033[91m"   # error

def _ts():
    return f"{DIM}{time.strftime('%H:%M:%S')}{RESET}"

def log(who: str, msg: str, color: str = ""):
    print(f"  {_ts()}  {color}{BOLD}{who:10}{RESET}  {msg}")

def ok(msg: str):
    print(f"  {_ts()}  {GREEN}✓{RESET}  {msg}")

def step(msg: str):
    print(f"\n{BOLD}── {msg}{RESET}")

# ── File helpers ───────────────────────────────────────────────────────────────

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]

# ── Main PoC ──────────────────────────────────────────────────────────────────

async def run_poc():
    results = []

    # ── Step 1: Start master ───────────────────────────────────────────────────
    step("1 · Master starts")
    master_topo = SwampTopology()
    master_topo.set_master()

    master_srv = SwampServer("Master", port=MASTER_PORT)
    master_srv.is_master = True

    # Track what master receives
    master_received_chat   = []
    master_received_files  = []
    master_file_chunks     = {}   # transfer_id -> [chunks]

    async def master_on_role(peer, header, payload, writer):
        role = header.get("role", "?")
        name = header.get("device_name", peer)
        log("Master", f"← ROLE_ANNOUNCE from {name!r} ({role})", AMBER)
        # Send STATE_SYNC + NODE_LIST back
        state = make_state_sync(
            chat_history=[{"text": "Welcome!", "sender": "Master", "timestamp": time.time()}],
            files_list=[],
            sync_items=[],
        )
        nodes = make_node_list(master_topo.to_node_list())
        writer.write(state)
        writer.write(nodes)
        await writer.drain()
        log("Master", f"→ STATE_SYNC + NODE_LIST sent to {name!r}", AMBER)

    async def master_on_chat(peer, header, payload, writer):
        text   = header.get("text", "")
        sender = header.get("sender", peer)
        master_received_chat.append((sender, text))
        log("Master", f"← CHAT from {sender!r}: {text!r}", AMBER)
        # Relay to all other connected nodes
        frame = make_chat(text, sender, header.get("timestamp", time.time()))
        await master_srv.broadcast(frame, exclude=peer)
        log("Master", f"→ relayed to {len(master_srv.get_connected_peers())-1} other node(s)", AMBER)

    async def master_on_file_meta(peer, header, payload, writer):
        tid = header.get("transfer_id", "?")
        fn  = header.get("filename", "?")
        sz  = header.get("filesize", 0)
        master_file_chunks[tid] = {"filename": fn, "size": sz, "chunks": {}, "total": None}
        log("Master", f"← FILE_META: {fn!r} ({sz:,} bytes)", AMBER)

    async def master_on_file_data(peer, header, payload, writer):
        tid   = header.get("transfer_id", "?")
        idx   = header.get("chunk_index", 0)
        total = header.get("total_chunks", 1)
        if tid in master_file_chunks:
            master_file_chunks[tid]["chunks"][idx] = payload
            master_file_chunks[tid]["total"] = total
            received = len(master_file_chunks[tid]["chunks"])
            if received == total:
                data = b"".join(
                    master_file_chunks[tid]["chunks"][i] for i in range(total)
                )
                master_received_files.append((master_file_chunks[tid]["filename"], data))
                log("Master", f"← FILE complete: {master_file_chunks[tid]['filename']!r} "
                              f"({len(data):,} bytes, sha256:{_sha256(data)})", AMBER)

    master_srv.set_handlers({
        MsgType.ROLE_ANNOUNCE: master_on_role,
        MsgType.CHAT:          master_on_chat,
        MsgType.FILE_META:     master_on_file_meta,
        MsgType.FILE_DATA:     master_on_file_data,
    })
    await master_srv.start()
    ok(f"Master server listening on port {MASTER_PORT}")

    await asyncio.sleep(0.1)

    # ── Step 2: Node A joins ───────────────────────────────────────────────────
    step("2 · Node A connects to master")
    node_a_received_chat  = []
    node_a_received_sync  = []

    client_a = SwampClient("NodeA")

    async def node_a_on_chat(peer, header, payload, writer):
        text   = header.get("text", "")
        sender = header.get("sender", peer)
        node_a_received_chat.append((sender, text))
        log("Node A", f"← CHAT from {sender!r}: {text!r}", BLUE)

    async def node_a_on_state_sync(peer, header, payload, writer):
        chat = header.get("chat_history", [])
        node_a_received_sync.extend(chat)
        log("Node A", f"← STATE_SYNC: {len(chat)} chat message(s) from master", BLUE)

    async def node_a_on_node_list(peer, header, payload, writer):
        nodes = header.get("nodes", [])
        log("Node A", f"← NODE_LIST: {len(nodes)} peer(s) on network", BLUE)

    client_a.set_handlers({
        MsgType.CHAT:       node_a_on_chat,
        MsgType.STATE_SYNC: node_a_on_state_sync,
        MsgType.NODE_LIST:  node_a_on_node_list,
    })

    ok_a = await client_a.connect("127.0.0.1", MASTER_PORT)
    assert ok_a, "Node A failed to connect"
    await client_a.start_listening()
    ok(f"Node A connected · peer identified as {client_a.peer_name!r}")

    # Announce role
    await client_a.send_message(make_role_announce("node", "NODE-A-001", "NodeA"))
    await asyncio.sleep(0.3)

    assert len(node_a_received_sync) >= 1, "STATE_SYNC not received"
    ok("Node A received STATE_SYNC with chat history from master")
    results.append("STATE_SYNC ✓")

    # ── Step 3: Node B joins ───────────────────────────────────────────────────
    step("3 · Node B connects to master")
    node_b_received_chat = []

    client_b = SwampClient("NodeB")

    async def node_b_on_chat(peer, header, payload, writer):
        text   = header.get("text", "")
        sender = header.get("sender", peer)
        node_b_received_chat.append((sender, text))
        log("Node B", f"← CHAT from {sender!r}: {text!r}", BLUE)

    async def node_b_on_state_sync(peer, header, payload, writer):
        chat = header.get("chat_history", [])
        log("Node B", f"← STATE_SYNC: {len(chat)} message(s)", BLUE)

    async def node_b_on_node_list(peer, header, payload, writer):
        nodes = header.get("nodes", [])
        log("Node B", f"← NODE_LIST: {len(nodes)} peer(s)", BLUE)

    client_b.set_handlers({
        MsgType.CHAT:       node_b_on_chat,
        MsgType.STATE_SYNC: node_b_on_state_sync,
        MsgType.NODE_LIST:  node_b_on_node_list,
    })

    ok_b = await client_b.connect("127.0.0.1", MASTER_PORT)
    assert ok_b, "Node B failed to connect"
    await client_b.start_listening()
    ok(f"Node B connected · peer identified as {client_b.peer_name!r}")

    await client_b.send_message(make_role_announce("node", "NODE-B-002", "NodeB"))
    await asyncio.sleep(0.2)

    # ── Step 4: Node A sends a chat — master relays to Node B ────────────────
    step("4 · Node A sends chat → master relays to Node B")
    msg_text = "Hey Node B, can you see this?"
    log("Node A", f"→ CHAT: {msg_text!r}", BLUE)
    await client_a.send_message(make_chat(msg_text, "NodeA", time.time()))
    await asyncio.sleep(0.3)

    assert any(t == msg_text for _, t in node_b_received_chat), \
        f"Node B did not receive relayed chat. Got: {node_b_received_chat}"
    ok("Master relayed Node A's message to Node B ✓")
    results.append("chat relay ✓")

    # ── Step 5: Node B replies ────────────────────────────────────────────────
    step("5 · Node B replies → master relays to Node A")
    reply = "Loud and clear, Node A!"
    log("Node B", f"→ CHAT: {reply!r}", BLUE)
    await client_b.send_message(make_chat(reply, "NodeB", time.time()))
    await asyncio.sleep(0.3)

    assert any(t == reply for _, t in node_a_received_chat), \
        f"Node A did not receive relayed reply. Got: {node_a_received_chat}"
    ok("Master relayed Node B's reply to Node A ✓")
    results.append("bidirectional chat ✓")

    # ── Step 6: Node A sends a file ───────────────────────────────────────────
    step("6 · Node A sends a 500 KB file to master")
    file_data = os.urandom(500_000)
    original_hash = _sha256(file_data)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".bin", prefix="swamp_poc_") as f:
        f.write(file_data)
        file_path = f.name

    log("Node A", f"→ FILE: {os.path.basename(file_path)} "
                  f"({len(file_data):,} bytes, sha256:{original_hash})", BLUE)

    try:
        await client_a.send_file(file_path)
        await asyncio.sleep(1.0)
    finally:
        os.unlink(file_path)

    assert len(master_received_files) >= 1, "Master did not receive any file"
    fname, received_data = master_received_files[0]
    received_hash = _sha256(received_data)
    assert received_data == file_data, \
        f"File integrity mismatch! orig={original_hash} recv={received_hash}"
    ok(f"File received intact by master · sha256 match: {received_hash} ✓")
    results.append("file transfer ✓")

    # ── Step 7: Sync data ─────────────────────────────────────────────────────
    step("7 · Node B shares clipboard text")
    clip_received = []

    async def master_on_sync(peer, header, payload, writer):
        clip_received.append(header.get("payload", ""))
        log("Master", f"← SYNC_DATA clipboard: {header.get('payload', '')!r}", AMBER)

    master_srv.register_handler(MsgType.SYNC_DATA, master_on_sync)

    clip_text = "https://swamp.app — peer-to-peer mobile exchange"
    log("Node B", f"→ SYNC_DATA clipboard: {clip_text!r}", BLUE)
    msg = SyncDataMsg(data_type="clipboard", payload=clip_text)
    await client_b.send_message(encode_message(msg))
    await asyncio.sleep(0.2)

    assert clip_text in clip_received, f"Clipboard not received: {clip_received}"
    ok("Clipboard sync received by master ✓")
    results.append("sync data ✓")

    # ── Teardown ──────────────────────────────────────────────────────────────
    step("8 · Graceful disconnect")
    await client_a.disconnect()
    await client_b.disconnect()
    await asyncio.sleep(0.1)
    await master_srv.stop()
    log("Master", "server stopped", AMBER)
    ok("All connections closed cleanly ✓")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'─'*52}")
    print(f"{BOLD}{GREEN}  PoC PASSED{RESET}  —  {len(results)} scenarios verified")
    print(f"{'─'*52}")
    for r in results:
        print(f"    {GREEN}✓{RESET}  {r}")
    print(f"{'─'*52}\n")


if __name__ == "__main__":
    print(f"\n{BOLD}  SWAMP — Proof of Concept{RESET}")
    print(f"  {DIM}Master + 2 Nodes on localhost · no display needed{RESET}\n")
    asyncio.run(run_poc())
