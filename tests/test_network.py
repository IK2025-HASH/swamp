"""Tests for TCP server + client — connection, chat delivery, file transfer."""
import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.network.server import SwampServer
from src.network.client import SwampClient
from src.protocol import make_chat, make_role_announce, MsgType

# Each test gets its own port so they never collide even if a socket lingers.
_PORT_BASE = 54390


async def _make_pair(port):
    server = SwampServer("TestServer", port=port)
    await server.start()
    client = SwampClient("TestClient")
    ok = await client.connect("127.0.0.1", port)
    assert ok, "client connect failed"
    await client.start_listening()
    # Let HELLO exchange finish so server re-keys connection by name
    await asyncio.sleep(0.1)
    return server, client


async def _teardown(server, client):
    try:
        await client.disconnect()
    except Exception:
        pass
    try:
        await server.stop()
    except Exception:
        pass


def test_connect():
    async def run():
        server, client = await _make_pair(_PORT_BASE + 1)
        try:
            assert client._connected
            assert client.peer_name == "TestServer"
        finally:
            await _teardown(server, client)
    asyncio.run(run())


def test_chat_delivery():
    async def run():
        received = []
        server, client = await _make_pair(_PORT_BASE + 2)
        try:
            async def on_chat(peer, header, payload, writer):
                received.append(header.get("text"))

            server.register_handler(MsgType.CHAT, on_chat)
            await client.send_message(make_chat("ping", "TestClient", 1.0))
            await asyncio.sleep(0.2)
            assert "ping" in received, f"not received: {received}"
        finally:
            await _teardown(server, client)
    asyncio.run(run())


def test_server_sends_to_client():
    async def run():
        received = []
        server, client = await _make_pair(_PORT_BASE + 3)
        try:
            async def on_chat(peer, header, payload, writer):
                received.append(header.get("text"))

            client.register_handler(MsgType.CHAT, on_chat)

            # Confirm server knows the peer by name after HELLO exchange
            connected = server.get_connected_peers()
            assert "TestClient" in connected, f"peers: {connected}"

            await server.send_to_peer("TestClient", make_chat("pong", "TestServer", 1.0))
            await asyncio.sleep(0.2)
            assert "pong" in received, f"not received: {received}"
        finally:
            await _teardown(server, client)
    asyncio.run(run())


def test_file_transfer():
    async def run():
        meta_received = []
        chunks_received = []
        server, client = await _make_pair(_PORT_BASE + 4)
        try:
            async def on_meta(peer, header, payload, writer):
                meta_received.append(header)

            async def on_data(peer, header, payload, writer):
                chunks_received.append(len(payload))

            server.register_handler(MsgType.FILE_META, on_meta)
            server.register_handler(MsgType.FILE_DATA, on_data)

            with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as f:
                f.write(b"A" * 200_000)   # 200 KB — forces multiple 64 KB chunks
                path = f.name

            try:
                await client.send_file(path)
                await asyncio.sleep(0.5)
            finally:
                os.unlink(path)

            assert len(meta_received) == 1
            assert meta_received[0]["filesize"] == 200_000
            assert sum(chunks_received) == 200_000
        finally:
            await _teardown(server, client)
    asyncio.run(run())


def test_role_announce_delivery():
    async def run():
        received = []
        server, client = await _make_pair(_PORT_BASE + 5)
        try:
            async def on_role(peer, header, payload, writer):
                received.append(header)

            server.register_handler(MsgType.ROLE_ANNOUNCE, on_role)
            await client.send_message(make_role_announce("node", "NID001", "TestClient"))
            await asyncio.sleep(0.2)
            assert len(received) == 1
            assert received[0]["role"] == "node"
        finally:
            await _teardown(server, client)
    asyncio.run(run())


def test_broadcast():
    async def run():
        received_by_b = []
        received_by_c = []
        server = SwampServer("Hub", port=_PORT_BASE + 6)
        await server.start()

        client_b = SwampClient("Bob")
        client_c = SwampClient("Carol")
        await client_b.connect("127.0.0.1", _PORT_BASE + 6)
        await client_c.connect("127.0.0.1", _PORT_BASE + 6)
        await client_b.start_listening()
        await client_c.start_listening()
        await asyncio.sleep(0.1)   # let HELLO exchange finish

        try:
            async def on_chat_b(peer, header, payload, writer):
                received_by_b.append(header.get("text"))

            async def on_chat_c(peer, header, payload, writer):
                received_by_c.append(header.get("text"))

            client_b.register_handler(MsgType.CHAT, on_chat_b)
            client_c.register_handler(MsgType.CHAT, on_chat_c)

            await server.broadcast(make_chat("broadcast!", "Hub", 1.0))
            await asyncio.sleep(0.3)

            assert "broadcast!" in received_by_b, received_by_b
            assert "broadcast!" in received_by_c, received_by_c
        finally:
            await client_b.disconnect()
            await client_c.disconnect()
            await server.stop()
    asyncio.run(run())


if __name__ == "__main__":
    tests = [
        test_connect,
        test_chat_delivery,
        test_server_sends_to_client,
        test_file_transfer,
        test_role_announce_delivery,
        test_broadcast,
    ]
    passed = failed = 0
    for t in tests:
        try:
            t()
            print(f"  ✓  {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ✗  {t.__name__}: {e}")
            import traceback; traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed  {failed} failed")
    sys.exit(failed)
