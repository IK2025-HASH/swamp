"""
server.py — asyncio TCP server that accepts peer connections and dispatches
framed messages to registered handler callbacks.
"""

import asyncio
import logging
from typing import Callable, Dict, Optional, Any

from src.protocol import read_frame, make_hello, MsgType

logger = logging.getLogger(__name__)

SERVER_HOST = "0.0.0.0"
SERVER_PORT = 54321


class SwampServer:
    """
    Asyncio TCP server.

    Usage:
        server = SwampServer(device_name="Alice")
        server.register_handler(MsgType.CHAT, my_chat_handler)
        await server.start()
        ...
        await server.stop()

    Handler signature:
        async def handler(peer_name: str, header: dict, payload: bytes, writer: asyncio.StreamWriter)
    """

    def __init__(self, device_name: str, host: str = SERVER_HOST, port: int = SERVER_PORT):
        self.device_name = device_name
        self.host = host
        self.port = port
        self._server: Optional[asyncio.AbstractServer] = None
        self._handlers: Dict[str, Callable] = {}
        self._connections: Dict[str, asyncio.StreamWriter] = {}  # peer_name -> writer
        self._running = False

    # ------------------------------------------------------------------
    # Handler registration
    # ------------------------------------------------------------------

    def register_handler(self, msg_type: str, handler: Callable):
        """Register an async handler for a given message type."""
        self._handlers[msg_type] = handler

    def set_handlers(self, handlers: Dict[str, Callable]):
        """Register multiple handlers at once."""
        self._handlers.update(handlers)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self):
        """Start the TCP server."""
        if self._running:
            return
        self._server = await asyncio.start_server(
            self._handle_client,
            self.host,
            self.port,
            reuse_address=True,
        )
        self._running = True
        addr = self._server.sockets[0].getsockname()
        logger.info("SwampServer listening on %s:%d", addr[0], addr[1])

    async def stop(self):
        """Gracefully stop the server and close all connections."""
        self._running = False
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        for writer in list(self._connections.values()):
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
        self._connections.clear()
        logger.info("SwampServer stopped")

    # ------------------------------------------------------------------
    # Connection info
    # ------------------------------------------------------------------

    def get_connected_peers(self):
        """Return list of currently connected peer names."""
        return list(self._connections.keys())

    async def send_to_peer(self, peer_name: str, frame: bytes):
        """Send a pre-encoded frame to a named peer."""
        writer = self._connections.get(peer_name)
        if writer is None:
            raise KeyError(f"Peer '{peer_name}' not connected")
        writer.write(frame)
        await writer.drain()

    # ------------------------------------------------------------------
    # Internal: client handling
    # ------------------------------------------------------------------

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        peer_addr = writer.get_extra_info("peername")
        logger.info("New connection from %s", peer_addr)
        peer_name = str(peer_addr)  # updated once we receive HELLO

        # Send our HELLO first
        try:
            writer.write(make_hello(self.device_name))
            await writer.drain()
        except Exception as e:
            logger.error("Failed to send HELLO to %s: %s", peer_addr, e)
            writer.close()
            return

        try:
            while self._running:
                try:
                    header, payload = await asyncio.wait_for(
                        read_frame(reader), timeout=300.0  # 5-min idle timeout
                    )
                except asyncio.TimeoutError:
                    logger.info("Peer %s timed out", peer_name)
                    break
                except asyncio.IncompleteReadError:
                    logger.info("Peer %s disconnected", peer_name)
                    break
                except Exception as e:
                    logger.error("Frame read error from %s: %s", peer_name, e)
                    break

                msg_type = header.get("type", "")

                # Handle HELLO to learn peer name
                if msg_type == MsgType.HELLO:
                    new_name = header.get("device_name", peer_name)
                    logger.info("Peer identified as '%s'", new_name)
                    # Re-key connection dict
                    if peer_name in self._connections:
                        del self._connections[peer_name]
                    peer_name = new_name
                    self._connections[peer_name] = writer

                # Dispatch to registered handler
                handler = self._handlers.get(msg_type)
                if handler:
                    try:
                        await handler(peer_name, header, payload, writer)
                    except Exception as e:
                        logger.error(
                            "Handler error for msg_type=%s from %s: %s",
                            msg_type, peer_name, e,
                        )
                else:
                    logger.debug("No handler for msg_type=%s from %s", msg_type, peer_name)

        finally:
            # Clean up connection entry
            if self._connections.get(peer_name) is writer:
                del self._connections[peer_name]
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass
            logger.info("Connection closed for peer '%s'", peer_name)

            # Notify connection-close handler if registered
            close_handler = self._handlers.get("_DISCONNECT")
            if close_handler:
                try:
                    await close_handler(peer_name, {}, b"", None)
                except Exception as e:
                    logger.error("Disconnect handler error: %s", e)
