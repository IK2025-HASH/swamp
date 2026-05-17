"""
devices.py — DevicesScreen: scrollable peer list with role badges.

Master peers show an amber ★ badge; nodes show a blue ⊙ badge.
Nodes auto-connect to the master when one is discovered; manual
Connect buttons let users open direct node-to-node links.
"""

import logging

from kivy.clock import Clock
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.graphics import Color, Rectangle, RoundedRectangle

logger = logging.getLogger(__name__)

C_BG     = (0.08, 0.10, 0.12, 1)
C_PANEL  = (0.13, 0.16, 0.20, 1)
C_MASTER = (0.95, 0.60, 0.10, 1)
C_NODE   = (0.15, 0.65, 0.85, 1)
C_CONN   = (0.15, 0.50, 0.35, 1)
C_NAV    = (0.20, 0.24, 0.28, 1)


class PeerRow(BoxLayout):
    def __init__(self, peer_name: str, ip: str, port: int, role: str, on_connect, **kwargs):
        super().__init__(
            orientation="horizontal",
            size_hint_y=None, height=68,
            spacing=10, padding=(10, 8),
            **kwargs,
        )
        self.peer_name = peer_name
        self.ip = ip
        self.port = port
        self.role = role

        with self.canvas.before:
            Color(*C_PANEL)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[8])
        self.bind(pos=self._upd, size=self._upd)

        # Role badge
        badge_color = C_MASTER if role == "master" else C_NODE
        badge_text  = "★ MASTER" if role == "master" else "⊙ NODE"
        badge = Label(
            text=f"[b]{badge_text}[/b]",
            markup=True, font_size="11sp",
            color=badge_color,
            size_hint=(None, None), width=80, height=68,
            halign="center", valign="middle",
        )
        badge.bind(size=lambda w, s: setattr(w, "text_size", s))
        self.add_widget(badge)

        # Info column
        info = BoxLayout(orientation="vertical", spacing=2)
        name_lbl = Label(
            text=f"[b]{peer_name}[/b]",
            markup=True, halign="left", font_size="16sp", color=(1, 1, 1, 1),
        )
        name_lbl.bind(size=lambda w, s: setattr(w, "text_size", (s[0], None)))
        addr_lbl = Label(
            text=f"{ip}:{port}",
            halign="left", font_size="12sp", color=(0.5, 0.5, 0.5, 1),
        )
        addr_lbl.bind(size=lambda w, s: setattr(w, "text_size", (s[0], None)))
        info.add_widget(name_lbl)
        info.add_widget(addr_lbl)
        self.add_widget(info)

        # Connect button (hidden for master when auto-connected)
        self.connect_btn = Button(
            text="Connect",
            size_hint=(None, None), width=100, height=44,
            font_size="13sp",
            background_color=badge_color,
            background_normal="",
        )
        self.connect_btn.bind(on_press=lambda _: on_connect(peer_name, ip, port))
        self.add_widget(self.connect_btn)

    def _upd(self, *_):
        self._bg.pos = self.pos
        self._bg.size = self.size

    def mark_connected(self):
        self.connect_btn.text = "Connected"
        self.connect_btn.background_color = C_CONN
        self.connect_btn.disabled = True

    def mark_disconnected(self):
        self.connect_btn.text = "Connect"
        self.connect_btn.background_color = (
            C_MASTER if self.role == "master" else C_NODE
        )
        self.connect_btn.disabled = False

    def update_role(self, role: str):
        self.role = role


class DevicesScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app_ref = None
        self._peer_rows: dict = {}   # name -> PeerRow
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        with self.canvas.before:
            Color(*C_BG)
            self._bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._upd_bg, size=self._upd_bg)

        root = BoxLayout(orientation="vertical", padding=(16, 12), spacing=12)

        # Header
        header = BoxLayout(orientation="horizontal", size_hint_y=None, height=56, spacing=12)
        back_btn = Button(
            text="← Home", size_hint=(None, 1), width=100,
            font_size="14sp", background_color=C_NAV, background_normal="",
        )
        back_btn.bind(on_press=lambda _: self._go("home"))
        header.add_widget(back_btn)

        header.add_widget(Label(
            text="[b]Network Nodes[/b]", markup=True,
            font_size="20sp", color=(1, 1, 1, 1),
        ))

        refresh_btn = Button(
            text="Refresh", size_hint=(None, 1), width=90,
            font_size="14sp", background_color=(0.18, 0.55, 0.85, 1),
            background_normal="",
        )
        refresh_btn.bind(on_press=lambda _: self._refresh_peers())
        header.add_widget(refresh_btn)
        root.add_widget(header)

        self.status_lbl = Label(
            text="No peers found · ensure devices are on the same WiFi.",
            font_size="13sp", color=(0.5, 0.5, 0.5, 1),
            size_hint_y=None, height=36, halign="center",
        )
        self.status_lbl.bind(size=lambda w, s: setattr(w, "text_size", (s[0], None)))
        root.add_widget(self.status_lbl)

        scroll = ScrollView(bar_width=4)
        self.peer_list = BoxLayout(
            orientation="vertical", spacing=8, padding=(0, 4),
            size_hint_y=None,
        )
        self.peer_list.bind(minimum_height=self.peer_list.setter("height"))
        scroll.add_widget(self.peer_list)
        root.add_widget(scroll)

        self.add_widget(root)

    def _upd_bg(self, *_):
        self._bg.pos = self.pos
        self._bg.size = self.size

    def _go(self, name):
        if self.manager:
            self.manager.current = name

    # ------------------------------------------------------------------
    # Peer management (all thread-safe via Clock)
    # ------------------------------------------------------------------

    def add_peer(self, name: str, ip: str, port: int, role: str = "node"):
        Clock.schedule_once(lambda dt: self._add_peer_ui(name, ip, port, role))

    def remove_peer(self, name: str):
        Clock.schedule_once(lambda dt: self._remove_peer_ui(name))

    def update_peer_role(self, name: str, role: str):
        Clock.schedule_once(lambda dt: self._update_role_ui(name, role))

    def mark_peer_connected(self, name: str):
        Clock.schedule_once(lambda dt: self._mark_connected_ui(name))

    def _add_peer_ui(self, name: str, ip: str, port: int, role: str):
        if name in self._peer_rows:
            return
        row = PeerRow(
            peer_name=name, ip=ip, port=port, role=role,
            on_connect=self._on_connect,
        )
        self._peer_rows[name] = row
        self.peer_list.add_widget(row)
        self._update_status()

    def _remove_peer_ui(self, name: str):
        row = self._peer_rows.pop(name, None)
        if row:
            self.peer_list.remove_widget(row)
        self._update_status()

    def _update_role_ui(self, name: str, role: str):
        row = self._peer_rows.get(name)
        if row:
            row.update_role(role)

    def _mark_connected_ui(self, name: str):
        row = self._peer_rows.get(name)
        if row:
            row.mark_connected()

    def _refresh_peers(self):
        if not self.app_ref:
            return
        peers = self.app_ref.get_known_peers()
        self.peer_list.clear_widgets()
        self._peer_rows.clear()
        for peer_name, info in peers.items():
            self._add_peer_ui(
                peer_name, info.get("ip", ""), info.get("port", 54321),
                info.get("role", "node"),
            )
        self._update_status()

    def _update_status(self):
        count = len(self._peer_rows)
        masters = sum(1 for r in self._peer_rows.values() if r.role == "master")
        nodes   = count - masters
        if count == 0:
            self.status_lbl.text = "No peers · ensure devices share the same WiFi."
        else:
            parts = []
            if masters:
                parts.append(f"{masters} master")
            if nodes:
                parts.append(f"{nodes} node(s)")
            self.status_lbl.text = "  ·  ".join(parts) + " on network"

    # ------------------------------------------------------------------
    # Connect handler
    # ------------------------------------------------------------------

    def _on_connect(self, peer_name: str, ip: str, port: int):
        if self.app_ref:
            self.app_ref.connect_to_peer(peer_name, ip, port)
            self.mark_peer_connected(peer_name)
