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
from kivy.graphics import Color, Rectangle, RoundedRectangle

from src.ui.theme import (
    BG_BASE, BG_SURFACE, BG_RAISED,
    C_MASTER, C_NODE, C_SUCCESS,
    T_PRIMARY, T_SECONDARY, T_DIM,
    FS_XS, FS_SM, FS_MD, FS_LG,
    RADIUS_MD,
    H_BTN_SM, H_ROW,
    SPACE_SM, SPACE_MD,
)
from src.ui.widgets import SwampHeader, SwampButton, EmptyState, StatusDot

logger = logging.getLogger(__name__)


class PeerRow(BoxLayout):
    def __init__(self, peer_name: str, ip: str, port: int, role: str, on_connect, **kwargs):
        super().__init__(
            orientation="horizontal",
            size_hint_y=None, height=H_ROW,
            spacing=10, padding=(12, 8),
            **kwargs,
        )
        self.peer_name = peer_name
        self.ip = ip
        self.port = port
        self.role = role

        with self.canvas.before:
            Color(*BG_SURFACE)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=RADIUS_MD)
        self.bind(pos=self._upd, size=self._upd)

        # Role status dot
        badge_color = C_MASTER if role == "master" else C_NODE
        badge_text  = "★ MASTER" if role == "master" else "⊙ NODE"
        self._status_dot = StatusDot(text=badge_text, color=badge_color)
        self._status_dot.size_hint = (None, 1)
        self._status_dot.width = 100
        self.add_widget(self._status_dot)

        # Info column
        info = BoxLayout(orientation="vertical", spacing=2)
        name_lbl = Label(
            text=f"[b]{peer_name}[/b]",
            markup=True, halign="left", font_size=FS_LG, color=T_PRIMARY,
        )
        name_lbl.bind(size=lambda w, s: setattr(w, "text_size", (s[0], None)))
        addr_lbl = Label(
            text=f"{ip}:{port}",
            halign="left", font_size=FS_SM, color=T_DIM,
        )
        addr_lbl.bind(size=lambda w, s: setattr(w, "text_size", (s[0], None)))
        info.add_widget(name_lbl)
        info.add_widget(addr_lbl)
        self.add_widget(info)

        # Connect button
        self.connect_btn = SwampButton(
            text="Connect",
            color=badge_color,
            height=H_BTN_SM,
        )
        self.connect_btn.size_hint = (None, None)
        self.connect_btn.width = 100
        self.connect_btn.bind(on_press=lambda _: on_connect(peer_name, ip, port))
        self.add_widget(self.connect_btn)

    def _upd(self, *_):
        self._bg.pos = self.pos
        self._bg.size = self.size

    def mark_connected(self):
        self.connect_btn.text = "Connected"
        self.connect_btn.btn_color = C_SUCCESS
        self.connect_btn.disabled = True

    def mark_disconnected(self):
        c = C_MASTER if self.role == "master" else C_NODE
        self.connect_btn.text = "Connect"
        self.connect_btn.btn_color = c
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
            Color(*BG_BASE)
            self._bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._upd_bg, size=self._upd_bg)

        root = BoxLayout(orientation="vertical", padding=(16, 12), spacing=SPACE_SM)

        # Header
        self.header = SwampHeader(title="Network Nodes", back_screen="home")
        root.add_widget(self.header)

        self.status_lbl = Label(
            text="No peers found · ensure devices are on the same WiFi.",
            font_size=FS_SM, color=T_DIM,
            size_hint_y=None, height=36, halign="center",
        )
        self.status_lbl.bind(size=lambda w, s: setattr(w, "text_size", (s[0], None)))
        root.add_widget(self.status_lbl)

        # Stack: empty state + scroll in a shared area
        self._list_area = BoxLayout(orientation="vertical")

        self._empty_state = EmptyState(
            icon="⊙",
            title="No devices found",
            subtitle="Start the server and join the same WiFi",
        )
        self._list_area.add_widget(self._empty_state)

        scroll = ScrollView(bar_width=4)
        self.peer_list = BoxLayout(
            orientation="vertical", spacing=SPACE_SM, padding=(0, 4),
            size_hint_y=None,
        )
        self.peer_list.bind(minimum_height=self.peer_list.setter("height"))
        scroll.add_widget(self.peer_list)
        self._scroll = scroll
        # scroll starts hidden; shown when peers exist
        scroll.opacity = 0
        scroll.disabled = True
        self._list_area.add_widget(scroll)

        root.add_widget(self._list_area)
        self.add_widget(root)

    def on_enter(self, *args):
        self.header.set_manager(self.manager)

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
        self._update_empty_state()

    def _remove_peer_ui(self, name: str):
        row = self._peer_rows.pop(name, None)
        if row:
            self.peer_list.remove_widget(row)
        self._update_status()
        self._update_empty_state()

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
        self._update_empty_state()

    def _update_empty_state(self):
        has_peers = len(self._peer_rows) > 0
        self._empty_state.opacity = 0 if has_peers else 1
        self._empty_state.disabled = has_peers
        self._scroll.opacity = 1 if has_peers else 0
        self._scroll.disabled = not has_peers

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
