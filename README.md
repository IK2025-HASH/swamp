# Swamp — Mobile Exchange Network

A pure-Python peer-to-peer Android app built with **Kivy + Buildozer**.  
Devices on the same WiFi (or paired via QR) form a self-organising network:
one phone becomes the **Master** (hub), the rest join as **Nodes** (spokes) —
but every node operates independently even when the master is offline.

> Like a travel group with a shared bucket list: each traveller explores
> freely and syncs their itinerary back to the trip organiser.

---

## Features (current)

| Feature | Description |
|---|---|
| **Chat** | Real-time text messaging; master broadcasts to all nodes |
| **File Transfer** | Chunked send/receive with progress bar |
| **Data Sync** | Share contacts JSON or clipboard text across devices |
| **Screen Share** | JPEG-compressed frames streamed to connected peers |
| **Hub-and-Spoke** | Master ★ holds shared state, relays messages; Nodes ⊙ work offline too |
| **mDNS Discovery** | Auto-finds peers on the same WiFi via Zeroconf |
| **QR Pairing** | Scan a QR code to connect instantly — no WiFi discovery needed |

---

## Quick Start

### Desktop (development / testing)
```bash
pip install -r requirements.txt
python main.py
```

### Android (production)
```bash
pip install buildozer
buildozer android debug deploy run
```
Requires Android SDK/NDK; see [Buildozer docs](https://buildozer.readthedocs.io).

---

## Project Structure

```
swamp/
├── main.py                    # App entry point + SwampApp coordinator
├── buildozer.spec             # Android build config (API 33, arm64+armv7)
├── requirements.txt
└── src/
    ├── protocol.py            # Message framing + all message types
    ├── network/
    │   ├── discovery.py       # mDNS advertise + browse (Zeroconf)
    │   ├── server.py          # asyncio TCP server + master relay logic
    │   ├── client.py          # asyncio TCP client + file/frame send
    │   └── topology.py        # NodeRole, PeerInfo, SwampTopology
    ├── screens/
    │   ├── home.py            # Role selection (Master ★ / Node ⊙)
    │   ├── devices.py         # Peer list with role badges
    │   ├── chat.py            # Real-time chat
    │   ├── files.py           # File send/receive
    │   ├── sync.py            # Data sync + screen share
    │   └── qr_screen.py       # QR show + camera scan
    └── utils/
        ├── android_utils.py   # pyjnius helpers, storage paths
        └── qr_utils.py        # QR generate, decode, IP helper
```

---

## Architecture

```
Master device                     Node devices
┌──────────────────┐              ┌────────────┐
│  TCP Server :54321│◄────────────│  Client    │  Node A
│  mDNS: role=master│             └────────────┘
│  Shared state:    │
│  • chat_history   │             ┌────────────┐
│  • files_list     │◄────────────│  Client    │  Node B
│  • sync_items     │             └────────────┘
│                   │
│  On new join:     │    Direct node-to-node (optional)
│  → STATE_SYNC     │    ┌────────┐     ┌────────┐
│  → NODE_LIST      │    │ Node A │────►│ Node B │
│  → ROLE_ANNOUNCE  │    └────────┘     └────────┘
└──────────────────┘
```

See [DEVELOPMENT_PLAN.md](DEVELOPMENT_PLAN.md) for the full roadmap.
