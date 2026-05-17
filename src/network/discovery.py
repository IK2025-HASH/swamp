"""
discovery.py — mDNS/Zeroconf service advertisement and peer browsing.

Advertises:  _swamp._tcp.local.  on port 54321
Browses for: other _swamp._tcp.local. peers on the same network
"""

import asyncio
import logging
import socket
import threading
from typing import Callable, Dict, Optional

try:
    from zeroconf import (
        ServiceBrowser,
        ServiceInfo,
        Zeroconf,
        ServiceStateChange,
    )
    ZEROCONF_AVAILABLE = True
except ImportError:
    ZEROCONF_AVAILABLE = False
    logging.warning("zeroconf not available — peer discovery disabled")

logger = logging.getLogger(__name__)

SERVICE_TYPE = "_swamp._tcp.local."
SERVICE_PORT = 54321


def _get_local_ip() -> str:
    """Best-effort attempt to get the device's LAN IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class SwampDiscovery:
    """
    Manages Zeroconf advertising and browsing for Swamp peers.

    Callbacks:
        on_peer_added(name: str, ip: str, port: int)
        on_peer_removed(name: str)
    """

    def __init__(
        self,
        device_name: str,
        on_peer_added: Optional[Callable[[str, str, int], None]] = None,
        on_peer_removed: Optional[Callable[[str], None]] = None,
    ):
        self.device_name = device_name
        self.on_peer_added = on_peer_added
        self.on_peer_removed = on_peer_removed

        self._zeroconf: Optional["Zeroconf"] = None
        self._browser: Optional["ServiceBrowser"] = None
        self._service_info: Optional["ServiceInfo"] = None
        self._running = False
        self._lock = threading.Lock()
        self._peers: Dict[str, dict] = {}  # name -> {ip, port}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self):
        """Start advertising and browsing (blocking zeroconf init in calling thread)."""
        if not ZEROCONF_AVAILABLE:
            logger.warning("Zeroconf unavailable; discovery not started")
            return
        with self._lock:
            if self._running:
                return
            try:
                self._zeroconf = Zeroconf()
                self._advertise()
                self._browse()
                self._running = True
                logger.info("Discovery started for device '%s'", self.device_name)
            except Exception as e:
                logger.error("Failed to start discovery: %s", e)

    def stop(self):
        """Stop advertising and browsing."""
        with self._lock:
            if not self._running:
                return
            try:
                if self._service_info and self._zeroconf:
                    self._zeroconf.unregister_service(self._service_info)
                if self._zeroconf:
                    self._zeroconf.close()
            except Exception as e:
                logger.error("Error stopping discovery: %s", e)
            finally:
                self._zeroconf = None
                self._browser = None
                self._service_info = None
                self._running = False
                logger.info("Discovery stopped")

    def get_peers(self) -> Dict[str, dict]:
        """Return a snapshot of currently known peers."""
        with self._lock:
            return dict(self._peers)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _advertise(self):
        """Register the _swamp._tcp.local. service."""
        local_ip = _get_local_ip()
        # Service name must be unique; use device name + suffix
        service_name = f"{self.device_name}.{SERVICE_TYPE}"
        self._service_info = ServiceInfo(
            type_=SERVICE_TYPE,
            name=service_name,
            addresses=[socket.inet_aton(local_ip)],
            port=SERVICE_PORT,
            properties={
                "device": self.device_name.encode("utf-8"),
                "version": b"1.0",
            },
            server=f"{self.device_name}.local.",
        )
        self._zeroconf.register_service(self._service_info)
        logger.info("Advertised service '%s' at %s:%d", service_name, local_ip, SERVICE_PORT)

    def _browse(self):
        """Start browsing for _swamp._tcp.local. peers."""
        self._browser = ServiceBrowser(
            self._zeroconf,
            SERVICE_TYPE,
            handlers=[self._on_service_state_change],
        )

    def _on_service_state_change(
        self,
        zeroconf: "Zeroconf",
        service_type: str,
        name: str,
        state_change: "ServiceStateChange",
    ):
        """Called by Zeroconf thread when a service is added/removed."""
        # Extract just the device-friendly name (strip service type suffix)
        friendly = name.replace(f".{SERVICE_TYPE}", "").replace(SERVICE_TYPE, "")

        if state_change == ServiceStateChange.Added:
            info = zeroconf.get_service_info(service_type, name)
            if info:
                try:
                    ip = socket.inet_ntoa(info.addresses[0])
                except Exception:
                    ip = "unknown"
                port = info.port

                # Don't add ourselves
                if friendly == self.device_name:
                    return

                with self._lock:
                    self._peers[friendly] = {"ip": ip, "port": port}

                logger.info("Peer added: %s at %s:%d", friendly, ip, port)
                if self.on_peer_added:
                    try:
                        self.on_peer_added(friendly, ip, port)
                    except Exception as e:
                        logger.error("on_peer_added callback error: %s", e)

        elif state_change == ServiceStateChange.Removed:
            with self._lock:
                self._peers.pop(friendly, None)

            logger.info("Peer removed: %s", friendly)
            if self.on_peer_removed:
                try:
                    self.on_peer_removed(friendly)
                except Exception as e:
                    logger.error("on_peer_removed callback error: %s", e)
