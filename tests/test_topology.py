"""Tests for src/network/topology.py."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.network.topology import SwampTopology, NodeRole, PeerInfo


def _peer(node_id, name, role=NodeRole.NODE, ip="10.0.0.1"):
    return PeerInfo(node_id=node_id, name=name, ip=ip, port=54321, role=role)


def test_default_role_is_node():
    t = SwampTopology()
    assert t.role == NodeRole.NODE
    assert not t.is_master()


def test_set_master():
    t = SwampTopology()
    t.set_master()
    assert t.is_master()
    assert t.role == NodeRole.MASTER


def test_set_node_after_master():
    t = SwampTopology()
    t.set_master()
    t.set_node()
    assert not t.is_master()


def test_add_and_count_peers():
    t = SwampTopology()
    t.add_peer(_peer("A", "Alice"))
    t.add_peer(_peer("B", "Bob"))
    assert t.peer_count() == 2


def test_get_peer_by_name():
    t = SwampTopology()
    p = _peer("A", "Alice")
    t.add_peer(p)
    assert t.get_peer_by_name("Alice") is p
    assert t.get_peer_by_name("Nobody") is None


def test_get_peer_by_id():
    t = SwampTopology()
    p = _peer("X1", "Xena")
    t.add_peer(p)
    assert t.get_peer("X1") is p
    assert t.get_peer("??") is None


def test_remove_peer_by_name():
    t = SwampTopology()
    p = _peer("A", "Alice")
    t.add_peer(p)
    removed = t.remove_peer_by_name("Alice")
    assert removed is p
    assert t.peer_count() == 0


def test_remove_nonexistent_peer():
    t = SwampTopology()
    result = t.remove_peer_by_name("Ghost")
    assert result is None


def test_get_master_peer():
    t = SwampTopology()
    t.add_peer(_peer("M", "Master", role=NodeRole.MASTER))
    t.add_peer(_peer("N", "Node",   role=NodeRole.NODE))
    m = t.get_master()
    assert m is not None and m.name == "Master"


def test_get_nodes():
    t = SwampTopology()
    t.add_peer(_peer("M", "Master", role=NodeRole.MASTER))
    t.add_peer(_peer("N1", "Node1", role=NodeRole.NODE))
    t.add_peer(_peer("N2", "Node2", role=NodeRole.NODE))
    nodes = t.get_nodes()
    assert len(nodes) == 2
    names = {p.name for p in nodes}
    assert "Node1" in names and "Node2" in names


def test_to_node_list():
    t = SwampTopology()
    t.add_peer(_peer("A", "Alice", role=NodeRole.MASTER))
    t.add_peer(_peer("B", "Bob"))
    nl = t.to_node_list()
    assert len(nl) == 2
    names = {e["name"] for e in nl}
    assert "Alice" in names and "Bob" in names


def test_from_node_list_round_trip():
    t1 = SwampTopology()
    t1.add_peer(_peer("A", "Alice", role=NodeRole.MASTER))
    t1.add_peer(_peer("B", "Bob"))
    nl = t1.to_node_list()

    t2 = SwampTopology()
    t2.from_node_list(nl)
    assert t2.peer_count() == 2
    alice = t2.get_peer_by_name("Alice")
    assert alice is not None
    assert alice.role == NodeRole.MASTER


def test_update_direct_flag():
    t = SwampTopology()
    p = _peer("A", "Alice")
    t.add_peer(p)
    t.update_direct("A", True)
    assert t.get_peer("A").is_direct is True


def test_node_id_is_set():
    t = SwampTopology()
    assert len(t.node_id) > 0


if __name__ == "__main__":
    import sys
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
