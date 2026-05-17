"""
client.py — asyncio TCP client for connecting to a Swamp peer.

Provides:
  connect(ip, port)        — establish connection, exchange HELLO
  send_message(frame)      — send a pre-encoded frame
  send_file(path, cb)      — chunk and stream a file with progress callback
  disconnect()             — close the connection
  listen(handlers)         — receive loop dispatching to handler dict
"""

import asyncio
import logging
import os
import time
import uuid
from typing import Callable, Dict, Optional

from src.protocol import (
    read_frame,
    encode_message,
    make_hello,
    make_ack,
    MsgType,
    FileMetaMsg,
    FileDataMsg,
)

logger = logging.getLogger(__name__)

CHUNK_SIZE = 64 * 1024  # 64 KB per chunk


class SwampClient:
    """
    Asyncio TCP client for a single peer connection.

    Usage:
        client = SwampClient("MyDevice")
        await client.connect("192.168.1.5", 54321)
        await client.send_message(make_chat("hello", "MyDevice", time.time()))
        await client.send_file("/path/to/file.jpg", progress_cb=my_cb)
        await client.disconnect()
    """

    def __init__(self, device_name: str):
        self.device_name = device_name
        self.peer_name: Optional[str] = None
        self.peer_ip: Optional[str] = None
        self.peer_port: Optional[int] = None

        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._connected = False
        self._handlers: Dict[str, Callable] = {}
        self._listen_task: Optional[asyncio.Task] = None
        self._write_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self, ip: str, port: int = 54321) -> bool:
        """
        Establish TCP connection and exchange HELLO frames.
        Returns True on success.
        """
        if self._connected:
            await self.disconnect()
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(ip, port),
                timeout=10.0,
            )
            self.peer_ip = ip
            self.peer_port = port

            # Send our HELLO
            self._writer.write(make_hello(self.device_name))
            await self._writer.drain()

            # Wait for peer's HELLO
            header, _ = await asyncio.wait_for(read_frame(self._reader), timeout=10.0)
            if header.get("type") == MsgType.HELLO:
                self.peer_name = header.get("device_name", ip)
            else:
                self.peer_name = ip

            self._connected = True
            logger.info("Connected to '%s' at %s:%d", self.peer_name, ip, port)
            return True

        except Exception as e:
            logger.error("Connection to %s:%d failed: %s", ip, port, e)
            self._connected = False
            return False

    async def disconnect(self):
        """Close the connection."""
        self._connected = False
        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
            self._listen_task = None
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
            self._reader = None
        logger.info("Disconnected from peer '%s'", self.peer_name)

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    async def send_message(self, frame: bytes):
        """Send a pre-encoded wire frame."""
        if not self._connected or self._writer is None:
            raise RuntimeError("Not connected")
        async with self._write_lock:
            self._writer.write(frame)
            await self._writer.drain()

    async def send_file(
        self,
        file_path: str,
        progress_cb: Optional[Callable[[float], None]] = None,
        mime_type: str = "application/octet-stream",
    ) -> str:
        """
        Send a file in chunks.

        Args:
            file_path: Absolute path to the file.
            progress_cb: Called with progress 0.0–1.0 on each chunk sent.
            mime_type: MIME type hint.

        Returns:
            transfer_id (UUID string)
        """
        if not self._connected:
            raise RuntimeError("Not connected")

        file_path = os.path.abspath(file_path)
        filename = os.path.basename(file_path)
        filesize = os.path.getsize(file_path)
        transfer_id = str(uuid.uuid4())

        total_chunks = max(1, (filesize + CHUNK_SIZE - 1) // CHUNK_SIZE)

        # Send FILE_META
        meta = FileMetaMsg(
            filename=filename,
            filesize=filesize,
            mime_type=mime_type,
            transfer_id=transfer_id,
        )
        await self.send_message(encode_message(meta))
        logger.info("Sending file '%s' (%d bytes) id=%s", filename, filesize, transfer_id)

        # Send chunks
        bytes_sent = 0
        with open(file_path, "rb") as f:
            chunk_index = 0
            while True:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break
                chunk_msg = FileDataMsg(
                    transfer_id=transfer_id,
                    chunk_index=chunk_index,
                    total_chunks=total_chunks,
                    chunk_size=len(chunk),
                )
                frame = encode_message(chunk_msg, chunk)
                await self.send_message(frame)
                bytes_sent += len(chunk)
                chunk_index += 1

                if progress_cb:
                    progress = bytes_sent / filesize if filesize > 0 else 1.0
                    try:
                        progress_cb(progress)
                    except Exception:
                        pass

                # Yield to event loop to avoid blocking
                await asyncio.sleep(0)

        logger.info("File '%s' sent (%d chunks)", filename, total_chunks)
        return transfer_id

    async def send_screen_frame(self, jpeg_bytes: bytes, frame_index: int, width: int, height: int):
        """Send a single compressed JPEG screen frame."""
        from src.protocol import ScreenFrameMsg, encode_message as _enc
        msg = ScreenFrameMsg(
            frame_index=frame_index,
            width=width,
            height=height,
            chunk_size=len(jpeg_bytes),
        )
        frame = _enc(msg, jpeg_bytes)
        await self.send_message(frame)

    # ------------------------------------------------------------------
    # Receiving
    # ------------------------------------------------------------------

    def register_handler(self, msg_type: str, handler: Callable):
        self._handlers[msg_type] = handler

    def set_handlers(self, handlers: Dict[str, Callable]):
        self._handlers.update(handlers)

    async def start_listening(self):
        """Start a background task to receive messages."""
        if self._listen_task and not self._listen_task.done():
            return
        self._listen_task = asyncio.create_task(self._receive_loop())

    async def _receive_loop(self):
        """Internal receive loop; dispatches frames to handlers."""
        logger.info("Client receive loop started for peer '%s'", self.peer_name)
        try:
            while self._connected and self._reader:
                try:
                    header, payload = await asyncio.wait_for(
                        read_frame(self._reader), timeout=300.0
                    )
                except asyncio.TimeoutError:
                    logger.info("Receive loop timeout for peer '%s'", self.peer_name)
                    break
                except asyncio.IncompleteReadError:
                    logger.info("Peer '%s' closed connection", self.peer_name)
                    break
                except Exception as e:
                    logger.error("Receive error from '%s': %s", self.peer_name, e)
                    break

                msg_type = header.get("type", "")
                handler = self._handlers.get(msg_type)
                if handler:
                    try:
                        await handler(self.peer_name, header, payload, self._writer)
                    except Exception as e:
                        logger.error("Handler error msg_type=%s: %s", msg_type, e)

        finally:
            self._connected = False
            logger.info("Client receive loop ended for peer '%s'", self.peer_name)
            disc_handler = self._handlers.get("_DISCONNECT")
            if disc_handler:
                try:
                    await disc_handler(self.peer_name, {}, b"", None)
                except Exception:
                    pass
