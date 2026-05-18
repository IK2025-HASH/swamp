# Swamp — Development Plan

**Stack:** Python 3 · Kivy 2.3 · asyncio · Zeroconf · pyjnius · Buildozer  
**Target:** Android API 26–33 (arm64-v8a + armeabi-v7a) + desktop testing  
**Branch:** `claude/android-file-sharing-app-jNDL3`

---

## Vision

A fully offline-capable, peer-to-peer mobile exchange network.  
No cloud server. No accounts. Point phones at each other, swap anything.

The topology mirrors a travel group:
- **Master ★** = trip organiser — holds the shared itinerary, relays news to all
- **Node ⊙** = traveller — explores freely, syncs back when it meets the group

---

## Current State (Done)

| Area | What exists |
|---|---|
| Protocol | Length-prefixed JSON+binary frames; 12 message types |
| Transport | asyncio TCP server + client; concurrent connections |
| Discovery | Zeroconf mDNS (_swamp._tcp.local.); role + node_id in TXT |
| Topology | SwampTopology (NodeRole, PeerInfo, peer registry) |
| Master relay | Server forwards RELAY frames; broadcasts CHAT/SYNC to all nodes |
| STATE_SYNC | Master sends chat history + files + sync items to new node on join |
| Heartbeat | Node → master ping every 30 s |
| Screens | Home, Devices, Chat, Files, Sync, QR |
| QR Pairing | Show QR (qrcode+PIL) / Scan QR (Camera+pyzbar) / manual IP fallback |
| Android build | buildozer.spec targeting API 33 |

---

## Development Phases

---

### Phase 1 — Resilience  `[next]`

**Goal:** The network heals itself. No single point of failure.

#### 1.1 Master Failover / Leader Election
- When the master disconnects, remaining nodes run a simple **Bully algorithm**:
  - Each node broadcasts `ELECTION` with its `node_id`
  - Highest lexicographic `node_id` wins
  - Winner broadcasts `MASTER_CLAIM`, restarts its server as master
  - Other nodes reconnect to the new master
- New file: `src/network/election.py`
- New protocol messages: `ELECTION`, `MASTER_CLAIM`
- UI: DevicesScreen shows "Electing…" badge during transition

#### 1.2 Reconnect with Message Queue
- When a node loses connection to master, it queues outbound messages (chat, sync) locally
- On reconnect, the queue is replayed before STATE_SYNC
- New field in `SwampTopology`: `_offline_queue: deque`
- `SwampClient` wraps sends with retry logic (exponential backoff, max 5 attempts)

#### 1.3 Offline-First File Storage
- All received files already saved to `RECEIVE_DIR`
- Add `src/utils/file_index.py`: maintains a JSON manifest of received/sent files
- Manifest persists across restarts; FILES screen reads from manifest on load

---

### Phase 2 — Persistence  `[recommended second]`

**Goal:** Nothing is lost when the app restarts.

#### 2.1 SQLite Database
- New file: `src/utils/db.py`
- Tables:
  ```sql
  messages  (id, sender, text, timestamp, peer_id)
  files     (id, filename, size, sender, path, timestamp, direction)
  sync_items(id, data_type, payload, timestamp, peer_id)
  peers     (id, node_id, name, last_ip, last_port, role, last_seen)
  ```
- `SwampApp` initialises DB on startup; handlers write to DB on receive
- ChatScreen loads last 100 messages from DB on enter
- FilesScreen loads file manifest from DB

#### 2.2 Peer Memory
- Known peers (name → IP) persisted in the `peers` table
- DevicesScreen shows "last seen N minutes ago" for known-but-offline peers
- Reconnect button for known peers (bypasses mDNS)

#### 2.3 Settings Screen
- New screen: `src/screens/settings.py`
- Persisted in a JSON file: `~/.swamp/settings.json`
- Options:
  - Device name (pre-fills HomeScreen)
  - TCP port (default 54321)
  - Max chat history to keep (default 500)
  - Auto-connect to known master on startup (toggle)
  - Receive directory path

---

### Phase 3 — Security  `[third]`

**Goal:** All traffic is encrypted; devices authenticate each other.

#### 3.1 Key Pair per Device
- On first launch, generate an Ed25519 keypair via `cryptography` library
- Store private key in `~/.swamp/identity.key`
- Public key included in `HELLO` and `ROLE_ANNOUNCE` messages
- Public key fingerprint (first 8 hex chars) shown in DevicesScreen

#### 3.2 Noise_XX Handshake
- Wrap the asyncio TCP stream in a Noise protocol session after HELLO exchange
- Use `noiseprotocol` library (pure Python)
- Pattern: `Noise_XX` (mutual authentication, forward secrecy)
- After handshake, all subsequent frames are encrypted + MACed
- QR payload includes the device's public key; scanning = pinned trust

#### 3.3 Secure QR
- QR payload extended: `{"n":…,"ip":…,"p":…,"r":…,"id":…,"pk":"<hex pubkey>"}`
- On scan: public key is pinned; future connections verify identity
- "Trust On First Scan" model — similar to Signal's Safety Numbers

#### 3.4 File Integrity
- Each `FILE_META` includes `sha256` hash of the complete file
- Receiver verifies hash after reassembly; shows ✓ or ✗ on FilesScreen

---

### Phase 4 — Android Native Integration  `[fourth]`

**Goal:** Full Android citizen — real file picker, contacts, background, WiFi Direct.

#### 4.1 File Picker (Android MediaStore)
```python
# src/utils/android_utils.py
def pick_file():
    # Intent.ACTION_GET_CONTENT via pyjnius
    Intent = autoclass('android.content.Intent')
    intent = Intent(Intent.ACTION_GET_CONTENT)
    intent.setType("*/*")
    activity.startActivityForResult(intent, REQUEST_FILE)
```
- `FilesScreen` "Pick File" button uses native picker instead of path TextInput
- Result callback wired via `android.activity.bind(on_activity_result=…)`

#### 4.2 Contacts Access
```python
# src/utils/android_utils.py
def read_contacts():
    # ContentResolver query on ContactsContract via pyjnius
```
- SyncScreen "Sync Contacts" reads real device contacts (with READ_CONTACTS permission)
- Serialises to JSON; sent as SYNC_DATA message

#### 4.3 Android Background Service
- Long-running TCP server should survive screen-off and app backgrounding
- New file: `src/android_service.py`
- Uses Kivy's `android.service` support or a raw `android.app.Service` via pyjnius
- Service holds the server + discovery; app UI binds to it on foreground

#### 4.4 WiFi Direct (P2P without router)
- Uses `android.net.wifi.p2p.WifiP2pManager` via pyjnius
- Enables pairing when no WiFi router is present (two phones directly)
- Supplements, not replaces, the existing WiFi LAN mode
- New file: `src/network/wifi_direct.py`

#### 4.5 Notifications
```python
# On new chat message while app is backgrounded:
NotificationManager → show notification with sender + preview
```
- Uses `android.app.NotificationManager` via pyjnius
- Tapping notification navigates to ChatScreen

---

### Phase 5 — UX Polish  `[fifth]`

**Goal:** App feels native and delightful on a phone.

#### 5.1 Chat Bubbles
- ChatScreen: right-aligned green bubbles for own messages, left-aligned dark bubbles for others
- Rounded rectangle background via KV canvas instructions
- Timestamp below each bubble (HH:MM)
- "Delivered" / "Read" indicators (ACK-based)

#### 5.2 File Thumbnails
- FilesScreen: image files show a 64×64 thumbnail (PIL thumbnail)
- Non-image files show a mime-type icon (text, audio, video, binary)
- Long-press on file row → share / delete options

#### 5.3 Transfer Notifications
- File send: animated progress ring (Kivy canvas arc)
- File receive: notification + sound on completion
- Screen share: FPS counter overlay

#### 5.4 Animated Transitions
- Kivy `SlideTransition` between screens instead of FadeTransition
- Master/Node role buttons: ripple effect on press (canvas animation)

#### 5.5 Onboarding
- First launch: short 3-screen walkthrough (role explanation, QR demo, permissions)
- Persisted via settings: `first_launch: false`

---

### Phase 6 — Build & Release  `[final]`

**Goal:** Reproducible APK, signed, ready for distribution.

#### 6.1 Buildozer CI
- GitHub Actions workflow: `.github/workflows/build.yml`
- Builds debug APK on every push to `main`
- Uploads APK as workflow artifact
- Build matrix: arm64-v8a + armeabi-v7a

#### 6.2 APK Signing
- Release keystore stored as GitHub Actions secret
- `buildozer.spec` release stanza configured
- `buildozer android release` produces signed APK

#### 6.3 Version Management
- Semantic versioning in `buildozer.spec`: `version = MAJOR.MINOR.PATCH`
- Git tag triggers release build
- Changelog maintained in `CHANGELOG.md`

#### 6.4 F-Droid Metadata
- `metadata/org.swamp.swamp.yml` following F-Droid spec
- Reproducible build description
- Screenshots in `metadata/en-US/images/`

#### 6.5 Play Store (optional)
- `fastlane` config for automated Play Store uploads
- AAB (Android App Bundle) variant

---

## File Roadmap

Files to be created per phase:

```
Phase 1 — Resilience
  src/network/election.py         leader election (Bully algorithm)
  src/utils/file_index.py         file manifest persistence

Phase 2 — Persistence
  src/utils/db.py                 SQLite schema + CRUD helpers
  src/screens/settings.py         settings screen

Phase 3 — Security
  src/utils/crypto.py             Ed25519 keypair + Noise_XX wrapper
  src/utils/trust_store.py        pinned public keys

Phase 4 — Android Native
  src/android_service.py          background Android service
  src/network/wifi_direct.py      WiFi Direct (P2P) support

Phase 5 — UX
  assets/icons/                   mime-type icons
  assets/sounds/                  notification sounds
  src/screens/onboarding.py       first-launch walkthrough

Phase 6 — Build & Release
  .github/workflows/build.yml     CI build + APK artifact
  CHANGELOG.md                    release notes
  metadata/                       F-Droid metadata
```

---

## Protocol Message Reference

| Type | Direction | Purpose |
|---|---|---|
| `HELLO` | both | Announce device name on connect |
| `ROLE_ANNOUNCE` | both | Broadcast role + node_id |
| `NODE_LIST` | master→node | Full peer list sent on join |
| `STATE_SYNC` | master→node | Chat + files + sync history on join |
| `CHAT` | any | Text message |
| `FILE_META` | any | File transfer header (name, size, mime, sha256) |
| `FILE_DATA` | any | File chunk (binary payload) |
| `SYNC_DATA` | any | Contacts JSON or clipboard text |
| `SCREEN_FRAME` | any | JPEG-compressed screen frame |
| `RELAY` | node→master→node | Master forwards to target node |
| `HEARTBEAT` | node→master | Keepalive every 30 s |
| `ACK` | both | Generic acknowledgement |
| `ELECTION` | node→all | Leader election broadcast *(Phase 1)* |
| `MASTER_CLAIM` | winner→all | New master announcement *(Phase 1)* |

---

## Dependency Matrix

| Library | Use | Platform |
|---|---|---|
| `kivy` | UI framework | all |
| `zeroconf` | mDNS discovery | all |
| `pillow` | Image ops, QR, thumbnails | all |
| `qrcode[pil]` | QR generation | all |
| `pyzbar` | QR scanning | all (needs libzbar) |
| `pyjnius` | Android API access | Android only |
| `cryptography` | Ed25519 keypairs *(Phase 3)* | all |
| `noiseprotocol` | Noise_XX encryption *(Phase 3)* | all |

---

## Testing Strategy

### Desktop (always)
```bash
python main.py   # run two instances on different ports for local testing
```

### Android emulator
```bash
buildozer android debug
adb install bin/swamp-debug.apk
```

### Real device pair
- Two phones on the same WiFi → one as Master, one as Node
- Test: auto-discovery, STATE_SYNC, chat relay, file transfer, QR scan

### Unit tests (to add in Phase 2)
```
tests/
  test_protocol.py    # encode/decode round-trips
  test_topology.py    # peer registry, role transitions
  test_db.py          # SQLite CRUD helpers
  test_qr_utils.py    # payload encode/decode
```

---

## Priority Order

```
1. Phase 1.1  Master Failover          ← eliminates single point of failure
2. Phase 2.1  SQLite Persistence       ← nothing lost on restart
3. Phase 3.1  Key Pairs + Noise_XX     ← encrypted + authenticated traffic
4. Phase 4.3  Background Service       ← server survives screen-off
5. Phase 1.2  Reconnect Queue          ← offline message delivery
6. Phase 4.1  Native File Picker       ← proper Android UX
7. Phase 5.1  Chat Bubbles             ← polished feel
8. Phase 6.1  CI Build                 ← reproducible APK
9. Phase 4.4  WiFi Direct              ← no router needed
10. Phase 6.4 F-Droid                  ← open distribution
```
