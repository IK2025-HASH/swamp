"""
main.py — Swamp P2P Android app entry point.

Topology
────────
• One device runs as Master (hub): starts TCP server, holds shared state,
  relays messages between nodes, broadcasts to all connected nodes.
• Other devices run as Nodes (spokes): connect to master for sync; can
  also open direct connections to other nodes; work offline independently.
• Like a travel group bucket list — each traveler (node) explores freely
  and syncs the shared itinerary back to the trip organiser (master).

Thread model
────────────
• Kivy ScreenManager on the main thread.
• asyncio event loop in a dedicated daemon thread.
• Network I/O is fully async; UI updates go via Clock.schedule_once().
"""

import asyncio
import base64
import json
import logging
import os
import sys
import threading
import time

os.environ.setdefault("KIVY_NO_ENV_CONFIG", "1")

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.screenmanager import ScreenManager, FadeTransition
from kivy.utils import platform
from kivy.logger import Logger

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

from src.protocol import (
    MsgType,
    make_chat,
    make_ack,
    make_hello,
    make_role_announce,
    make_heartbeat,
    make_node_list,
    make_state_sync,
    encode_message,
    SyncDataMsg,
    ScreenFrameMsg,
)
from src.network.server import SwampServer
from src.network.client import SwampClient
from src.network.discovery import SwampDiscovery
from src.network.topology import SwampTopology, NodeRole, PeerInfo
from src.screens.home import HomeScreen
from src.screens.devices import DevicesScreen
from src.screens.chat import ChatScreen
from src.screens.files import FilesScreen
from src.screens.sync import SyncScreen
from src.utils.android_utils import ensure_swamp_dir, IS_ANDROID

RECEIVE_DIR = ensure_swamp_dir()
HEARTBEAT_INTERVAL = 30.0   # seconds between node → master pings


# ---------------------------------------------------------------------------
# SwampApp
# ---------------------------------------------------------------------------

class SwampApp(App):
    title = "Swamp"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.device_name: str = "SwampDevice"

        # asyncio infrastructure
        self._loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        self._loop_thread: threading.Thread = threading.Thread(
            target=self._run_loop, daemon=True, name="swamp-asyncio"
        )

        # Topology — owns role + peer registry
        self.topology = SwampTopology()

        # Network objects (one server always runs for inbound; client for outbound)
        self._server: SwampServer = SwampServer(self.device_name)
        self._client: SwampClient = SwampClient(self.device_name)
        self._discovery: SwampDiscovery = None  # built in start_as_*

        # File transfer state: transfer_id -> {meta, chunks}
        self._incoming_transfers: dict = {}

        # Shared state (master is authoritative; nodes receive via STATE_SYNC)
        self._chat_history: list = []          # [{text, sender, timestamp}]
        self._files_list: list = []            # [{filename, size, sender, timestamp}]
        self._sync_items: list = []            # [{data_type, payload, timestamp}]

        # UI screens (set in build())
        self._home: HomeScreen = None
        self._devices: DevicesScreen = None
        self._chat: ChatScreen = None
        self._files: FilesScreen = None
        self._sync: SyncScreen = None

        self._active_peer: str = ""
        self._heartbeat_task: asyncio.Task = None

    # ------------------------------------------------------------------
    # Kivy App lifecycle
    # ------------------------------------------------------------------

    def build(self):
        sm = ScreenManager(transition=FadeTransition(duration=0.15))

        self._home = HomeScreen(name="home")
        self._devices = DevicesScreen(name="devices")
        self._chat = ChatScreen(name="chat")
        self._files = FilesScreen(name="files")
        self._sync = SyncScreen(name="sync")

        for screen in (self._home, self._devices, self._chat, self._files, self._sync):
            screen.app_ref = self
            sm.add_widget(screen)

        sm.current = "home"
        self._loop_thread.start()
        self._register_server_handlers()
        return sm

    def on_stop(self):
        self._stop_network()
        self._loop.call_soon_threadsafe(self._loop.stop)

    # ------------------------------------------------------------------
    # asyncio loop thread
    # ------------------------------------------------------------------

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _run_async(self, coro):
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    # ------------------------------------------------------------------
    # Device name + role
    # ------------------------------------------------------------------

    def set_device_name(self, name: str):
        self.device_name = name
        self._server.device_name = name
        self._client.device_name = name
        self.topology.node_id = name[:8].upper()

    # ------------------------------------------------------------------
    # Start as Master
    # ------------------------------------------------------------------

    def start_as_master(self):
        """This device becomes the hub: runs server + advertises as master."""
        self.topology.set_master()
        self._server.is_master = True

        self._discovery = SwampDiscovery(
            device_name=self.device_name,
            node_id=self.topology.node_id,
            role="master",
            on_peer_added=self._on_peer_discovered,
            on_peer_removed=self._on_peer_lost,
        )

        async def _start():
            try:
                await self._server.start()
                self._discovery.start()
                Clock.schedule_once(lambda dt: self._home.set_status(
                    True, "master", f"Master running · '{self.device_name}'"))
            except Exception as e:
                logger.error("start_as_master: %s", e)
                Clock.schedule_once(lambda dt: self._home.set_status(
                    False, "idle", f"Error: {e}"))

        self._run_async(_start())

    # ------------------------------------------------------------------
    # Start as Node
    # ------------------------------------------------------------------

    def start_as_node(self):
        """This device is a node: runs its own server and discovers the master."""
        self.topology.set_node()
        self._server.is_master = False

        self._discovery = SwampDiscovery(
            device_name=self.device_name,
            node_id=self.topology.node_id,
            role="node",
            on_peer_added=self._on_peer_discovered,
            on_peer_removed=self._on_peer_lost,
        )

        async def _start():
            try:
                await self._server.start()
                self._discovery.start()
                Clock.schedule_once(lambda dt: self._home.set_status(
                    True, "node", f"Node · '{self.device_name}' · looking for master…"))
            except Exception as e:
                logger.error("start_as_node: %s", e)
                Clock.schedule_once(lambda dt: self._home.set_status(
                    False, "idle", f"Error: {e}"))

        self._run_async(_start())

    # ------------------------------------------------------------------
    # Stop
    # ------------------------------------------------------------------

    def _stop_network(self):
        if self._discovery:
            self._discovery.stop()
        self._run_async(self._async_stop())

    async def _async_stop(self):
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        await self._server.stop()
        await self._client.disconnect()

    def stop_all(self):
        self._stop_network()
        Clock.schedule_once(lambda dt: self._home.set_status(False, "idle", "Stopped"))

    # ------------------------------------------------------------------
    # Server message handlers
    # ------------------------------------------------------------------

    def _register_server_handlers(self):
        handlers = {
            MsgType.CHAT:          self._handle_chat,
            MsgType.FILE_META:     self._handle_file_meta,
            MsgType.FILE_DATA:     self._handle_file_data,
            MsgType.SYNC_DATA:     self._handle_sync_data,
            MsgType.SCREEN_FRAME:  self._handle_screen_frame,
            MsgType.ROLE_ANNOUNCE: self._handle_role_announce,
            MsgType.HEARTBEAT:     self._handle_heartbeat,
            MsgType.STATE_SYNC:    self._handle_state_sync,
            "_DISCONNECT":         self._handle_disconnect,
        }
        self._server.set_handlers(handlers)
        self._client.set_handlers(handlers)

    # ── topology handlers ──────────────────────────────────────────────

    async def _handle_role_announce(self, peer_name: str, header: dict, payload: bytes, writer):
        role = header.get("role", "node")
        node_id = header.get("node_id", peer_name)
        name = header.get("device_name", peer_name)

        peer = PeerInfo(
            node_id=node_id,
            name=name,
            ip="",  # filled by discovery
            port=54321,
            role=NodeRole(role),
            is_direct=True,
        )
        self.topology.add_peer(peer)

        if self.topology.is_master():
            # Send peer the current node list + shared state
            nodes = self.topology.to_node_list()
            writer.write(make_node_list(nodes))
            writer.write(make_state_sync(
                self._chat_history[-50:],
                self._files_list[-50:],
                self._sync_items[-20:],
            ))
            await writer.drain()
            # Also notify all other nodes of the new joiner
            announcement = make_role_announce(role, node_id, name)
            await self._server.broadcast(announcement, exclude=name)

        Clock.schedule_once(lambda dt: self._devices.update_peer_role(name, role))
        Clock.schedule_once(lambda dt: self._home.set_status(
            True, self.topology.role.value,
            f"Peers: {self.topology.peer_count()}"
        ))

    async def _handle_heartbeat(self, peer_name: str, header: dict, payload: bytes, writer):
        # Master just acknowledges; node resets its timer on any response
        pass

    async def _handle_state_sync(self, peer_name: str, header: dict, payload: bytes, writer):
        """Received by nodes when joining master."""
        chat = header.get("chat_history", [])
        files = header.get("files_list", [])
        sync = header.get("sync_items", [])

        self._chat_history = chat
        self._files_list = files
        self._sync_items = sync

        if self._chat and chat:
            for msg in chat[-30:]:
                self._chat.add_message(
                    msg.get("text", ""), msg.get("sender", "?"),
                    is_self=False, timestamp=msg.get("timestamp", 0)
                )
        if self._sync and sync:
            for item in sync[-5:]:
                self._sync.on_sync_data_received(
                    item.get("data_type", ""), item.get("payload", "")
                )
        logger.info("STATE_SYNC received: %d chats, %d files, %d sync items",
                    len(chat), len(files), len(sync))

    # ── content handlers ───────────────────────────────────────────────

    async def _handle_chat(self, peer_name: str, header: dict, payload: bytes, writer):
        text = header.get("text", "")
        sender = header.get("sender", peer_name)
        ts = header.get("timestamp", time.time())

        self._chat_history.append({"text": text, "sender": sender, "timestamp": ts})

        if self._chat:
            self._chat.add_message(text, sender, is_self=False, timestamp=ts)

        # Master re-broadcasts to all other nodes
        if self.topology.is_master():
            frame = make_chat(text, sender, ts)
            await self._server.broadcast(frame, exclude=peer_name)

    async def _handle_file_meta(self, peer_name: str, header: dict, payload: bytes, writer):
        transfer_id = header.get("transfer_id", "")
        filename = header.get("filename", "unknown")
        filesize = header.get("filesize", 0)
        self._incoming_transfers[transfer_id] = {
            "filename": filename, "filesize": filesize,
            "bytes_received": 0, "chunks": {}, "total_chunks": None,
            "sender": peer_name,
        }
        if self._files:
            self._files.on_file_meta(transfer_id, filename, filesize)

    async def _handle_file_data(self, peer_name: str, header: dict, payload: bytes, writer):
        transfer_id = header.get("transfer_id", "")
        chunk_index = header.get("chunk_index", 0)
        total_chunks = header.get("total_chunks", 1)

        info = self._incoming_transfers.get(transfer_id)
        if info is None:
            return

        info["chunks"][chunk_index] = payload
        info["bytes_received"] += len(payload)
        info["total_chunks"] = total_chunks

        if self._files:
            self._files.on_file_progress(transfer_id, info["bytes_received"])

        if len(info["chunks"]) == total_chunks:
            await self._save_incoming_file(transfer_id, info)

    async def _save_incoming_file(self, transfer_id: str, info: dict):
        filename = info["filename"]
        save_path = os.path.join(RECEIVE_DIR, filename)
        base, ext = os.path.splitext(save_path)
        counter = 1
        while os.path.exists(save_path):
            save_path = f"{base}_{counter}{ext}"
            counter += 1
        try:
            with open(save_path, "wb") as f:
                for i in range(info["total_chunks"]):
                    f.write(info["chunks"][i])
        except Exception as e:
            logger.error("_save_incoming_file: %s", e)
            return

        entry = {
            "filename": filename,
            "size": info["filesize"],
            "sender": info.get("sender", "?"),
            "timestamp": time.time(),
            "path": save_path,
        }
        self._files_list.append(entry)
        del self._incoming_transfers[transfer_id]
        if self._files:
            self._files.on_file_complete(transfer_id, save_path)

    async def _handle_sync_data(self, peer_name: str, header: dict, payload: bytes, writer):
        data_type = header.get("data_type", "")
        data_payload = header.get("payload", "")
        entry = {"data_type": data_type, "payload": data_payload, "timestamp": time.time()}
        self._sync_items.append(entry)
        if self._sync:
            self._sync.on_sync_data_received(data_type, data_payload)
        if self.topology.is_master():
            frame = encode_message(SyncDataMsg(data_type=data_type, payload=data_payload))
            await self._server.broadcast(frame, exclude=peer_name)

    async def _handle_screen_frame(self, peer_name: str, header: dict, payload: bytes, writer):
        width = header.get("width", 0)
        height = header.get("height", 0)
        if self._sync and payload:
            self._sync.on_screen_frame_received(payload, width, height)

    async def _handle_disconnect(self, peer_name: str, header: dict, payload: bytes, writer):
        removed = self.topology.remove_peer_by_name(peer_name)
        if removed:
            Clock.schedule_once(lambda dt: self._devices.remove_peer(peer_name))
        if peer_name == self._active_peer:
            self._active_peer = ""
            Clock.schedule_once(lambda dt: self._on_peer_gone(peer_name))
        Clock.schedule_once(lambda dt: self._home.set_status(
            True, self.topology.role.value,
            f"Peers: {self.topology.peer_count()}"
        ))

    def _on_peer_gone(self, peer_name: str):
        if self._chat:
            self._chat.add_message(
                f"[{peer_name} left]", "System", False, time.time()
            )

    # ------------------------------------------------------------------
    # Discovery callbacks
    # ------------------------------------------------------------------

    def _on_peer_discovered(self, name: str, ip: str, port: int,
                             role: str = "node", node_id: str = ""):
        logger.info("Discovered: %s (%s) @ %s:%d", name, role, ip, port)

        peer = PeerInfo(
            node_id=node_id or name,
            name=name, ip=ip, port=port,
            role=NodeRole(role),
        )
        self.topology.add_peer(peer)

        if self._devices:
            self._devices.add_peer(name, ip, port, role)

        # Node: auto-connect to master when discovered
        if not self.topology.is_master() and role == "master":
            Clock.schedule_once(lambda dt: self._home.set_status(
                True, "node", f"Master found: {name}  Connecting…"
            ))
            self.connect_to_peer(name, ip, port, auto=True)

    def _on_peer_lost(self, name: str):
        self.topology.remove_peer_by_name(name)
        if self._devices:
            self._devices.remove_peer(name)

    def get_known_peers(self) -> dict:
        return {
            k: {"ip": v.ip, "port": v.port, "role": v.role.value}
            for k, v in self.topology.get_peers().items()
        }

    # ------------------------------------------------------------------
    # Connect to peer
    # ------------------------------------------------------------------

    def connect_to_peer(self, peer_name: str, ip: str, port: int, auto: bool = False):
        async def _connect():
            success = await self._client.connect(ip, port)
            if success:
                self._active_peer = self._client.peer_name or peer_name
                await self._client.start_listening()

                # Announce our role to the peer
                frame = make_role_announce(
                    self.topology.role.value,
                    self.topology.node_id,
                    self.device_name,
                )
                await self._client.send_message(frame)

                # Update topology: mark direct link
                peer = self.topology.get_peer_by_name(peer_name)
                if peer:
                    self.topology.update_direct(peer.node_id, True)

                Clock.schedule_once(lambda dt: self._on_connected(self._active_peer, auto))
            else:
                Clock.schedule_once(lambda dt: self._show_status(
                    f"Failed to connect to {peer_name}"
                ))
        self._run_async(_connect())

    def _on_connected(self, peer_name: str, auto: bool = False):
        if self._chat:
            self._chat.set_peer(peer_name)
        if self._files:
            self._files.set_peer(peer_name)
        if self._sync:
            self._sync.set_peer(peer_name)
        if self._devices:
            self._devices.mark_peer_connected(peer_name)

        role_label = "master" if self.topology.is_master() else "node"
        if self._home:
            self._home.set_status(True, role_label,
                                  f"Connected to {peer_name}")

        # Navigate to devices (not chat) on auto-connect; user can then pick
        if not auto and self.root:
            self.root.current = "chat"

        # Start heartbeat if we are a node connected to master
        if not self.topology.is_master():
            self._run_async(self._start_heartbeat())

    # ------------------------------------------------------------------
    # Heartbeat (node → master)
    # ------------------------------------------------------------------

    async def _start_heartbeat(self):
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _heartbeat_loop(self):
        while self._client._connected:
            try:
                frame = make_heartbeat(self.topology.node_id, time.time())
                await self._client.send_message(frame)
            except Exception:
                break
            await asyncio.sleep(HEARTBEAT_INTERVAL)

    # ------------------------------------------------------------------
    # Send helpers
    # ------------------------------------------------------------------

    def send_chat_message(self, text: str, peer_name: str = ""):
        async def _send():
            frame = make_chat(text, self.device_name, time.time())
            try:
                if self._client._connected:
                    await self._client.send_message(frame)
                else:
                    target = peer_name or self._active_peer
                    await self._server.send_to_peer(target, frame)
            except Exception as e:
                logger.error("send_chat_message: %s", e)
                Clock.schedule_once(lambda dt: self._show_status(f"Send failed: {e}"))
        self._run_async(_send())

    def send_file(self, file_path: str, progress_cb=None):
        async def _send():
            try:
                if self._client._connected:
                    await self._client.send_file(file_path, progress_cb=progress_cb)
                else:
                    Clock.schedule_once(lambda dt: self._show_status("Not connected to a peer"))
            except Exception as e:
                logger.error("send_file: %s", e)
                Clock.schedule_once(lambda dt: self._show_status(f"File send failed: {e}"))
        self._run_async(_send())

    def send_sync_data(self, data_type: str, payload: str):
        async def _send():
            msg = SyncDataMsg(data_type=data_type, payload=payload)
            frame = encode_message(msg)
            try:
                if self._client._connected:
                    await self._client.send_message(frame)
                elif self._active_peer:
                    await self._server.send_to_peer(self._active_peer, frame)
            except Exception as e:
                logger.error("send_sync_data: %s", e)
        self._run_async(_send())

    def send_screen_frame(self, jpeg_bytes: bytes, frame_index: int, width: int, height: int):
        async def _send():
            try:
                if self._client._connected:
                    await self._client.send_screen_frame(jpeg_bytes, frame_index, width, height)
                elif self._active_peer:
                    from src.protocol import encode_message as _enc, ScreenFrameMsg
                    msg = ScreenFrameMsg(frame_index=frame_index, width=width,
                                        height=height, chunk_size=len(jpeg_bytes))
                    await self._server.send_to_peer(self._active_peer, _enc(msg, jpeg_bytes))
            except Exception as e:
                logger.debug("send_screen_frame: %s", e)
        self._run_async(_send())

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _show_status(self, msg: str):
        logger.info("Status: %s", msg)
        if self._home:
            self._home.status_lbl.text = msg


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    SwampApp().run()
