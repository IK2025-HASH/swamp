"""
topology.py — Hub-and-spoke topology management.

One Master, N independent Nodes.
  Master  — central coordinator; relays messages, maintains shared state,
             broadcasts to all connected nodes.
  Node    — connects to master for sync; can also form direct peer
             connections to other nodes; operates offline independently.
"""

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class NodeRole(str, Enum):
    MASTER = "master"
    NODE = "node"


@dataclass
class PeerInfo:
    node_id: str
    name: str
    ip: str
    port: int
    role: NodeRole
    connected_at: float = field(default_factory=time.time)
    is_direct: bool = False  # True if we have an active direct TCP connection


class SwampTopology:
    """
    Tracks this device's role and all known peers.
    Thread-safe via GIL-protected dict operations.
    """

    def __init__(self):
        self.node_id: str = str(uuid.uuid4())[:8].upper()
        self.role: NodeRole = NodeRole.NODE
        self._peers: Dict[str, PeerInfo] = {}  # node_id -> PeerInfo

    # ------------------------------------------------------------------
    # Role management
    # ------------------------------------------------------------------

    def set_master(self):
        self.role = NodeRole.MASTER

    def set_node(self):
        self.role = NodeRole.NODE

    def is_master(self) -> bool:
        return self.role == NodeRole.MASTER

    # ------------------------------------------------------------------
    # Peer registry
    # ------------------------------------------------------------------

    def add_peer(self, peer: PeerInfo):
        self._peers[peer.node_id] = peer

    def remove_peer(self, node_id: str) -> Optional[PeerInfo]:
        return self._peers.pop(node_id, None)

    def remove_peer_by_name(self, name: str) -> Optional[PeerInfo]:
        for nid, peer in list(self._peers.items()):
            if peer.name == name:
                del self._peers[nid]
                return peer
        return None

    def update_direct(self, node_id: str, is_direct: bool):
        if node_id in self._peers:
            self._peers[node_id].is_direct = is_direct

    def get_peer(self, node_id: str) -> Optional[PeerInfo]:
        return self._peers.get(node_id)

    def get_peer_by_name(self, name: str) -> Optional[PeerInfo]:
        for peer in self._peers.values():
            if peer.name == name:
                return peer
        return None

    def get_peers(self) -> Dict[str, PeerInfo]:
        return dict(self._peers)

    def get_master(self) -> Optional[PeerInfo]:
        for peer in self._peers.values():
            if peer.role == NodeRole.MASTER:
                return peer
        return None

    def get_nodes(self) -> List[PeerInfo]:
        return [p for p in self._peers.values() if p.role == NodeRole.NODE]

    def peer_count(self) -> int:
        return len(self._peers)

    def to_node_list(self) -> list:
        """Serialize peers for NODE_LIST message."""
        return [
            {
                "node_id": p.node_id,
                "name": p.name,
                "ip": p.ip,
                "port": p.port,
                "role": p.role.value,
            }
            for p in self._peers.values()
        ]

    def from_node_list(self, nodes: list):
        """Populate peers from a NODE_LIST payload (used by nodes on join)."""
        for n in nodes:
            peer = PeerInfo(
                node_id=n["node_id"],
                name=n["name"],
                ip=n["ip"],
                port=n["port"],
                role=NodeRole(n.get("role", "node")),
            )
            self._peers.setdefault(peer.node_id, peer)
