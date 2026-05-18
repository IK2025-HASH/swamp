"""
home.py — HomeScreen: device name, role selection (Master / Node), status.
"""

import logging
import socket

from kivy.clock import Clock
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.graphics import Color, Rectangle, RoundedRectangle

from src.ui.theme import (
    BG_BASE, BG_SURFACE, BG_RAISED,
    BG_INPUT,
    C_GREEN, C_MASTER, C_NODE, C_DANGER,
    T_PRIMARY, T_SECONDARY, T_DIM,
    FS_SM, FS_MD, FS_LG,
    RADIUS_MD,
    H_BTN, H_BTN_SM, H_INPUT, H_NAV,
    SPACE_SM, SPACE_MD,
)
from src.ui.widgets import SwampButton, StatusDot

logger = logging.getLogger(__name__)


class HomeScreen(Screen):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app_ref = None
        self._active_role = "idle"   # "idle" | "master" | "node"
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        with self.canvas.before:
            Color(*BG_BASE)
            self._bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._upd_bg, size=self._upd_bg)

        root = BoxLayout(orientation="vertical", padding=28, spacing=16)

        # ── Title ────────────────────────────────────────────────────
        root.add_widget(Label(
            text="[b]SWAMP[/b]",
            markup=True, font_size="44sp",
            color=C_GREEN,
            size_hint_y=None, height=78,
        ))
        root.add_widget(Label(
            text="Mobile Exchange Network",
            font_size="14sp", color=T_DIM,
            size_hint_y=None, height=26,
        ))

        root.add_widget(Label(size_hint_y=None, height=SPACE_SM))

        # ── Device name ───────────────────────────────────────────────
        root.add_widget(self._label("Device Name"))
        self.name_input = TextInput(
            hint_text="Enter device name…",
            multiline=False,
            size_hint_y=None, height=H_INPUT, font_size="16sp",
            background_color=BG_INPUT,
            foreground_color=T_PRIMARY,
            cursor_color=C_GREEN,
        )
        self.name_input.text = socket.gethostname().split(".")[0] or "SwampDevice"
        root.add_widget(self.name_input)

        # ── Role explanation ──────────────────────────────────────────
        self.role_lbl = Label(
            text="Choose a role to start",
            font_size=FS_SM, color=T_DIM,
            size_hint_y=None, height=24,
        )
        root.add_widget(self.role_lbl)

        # ── Status dot ────────────────────────────────────────────────
        self.status_dot = StatusDot(text="Idle", color=T_DIM)
        root.add_widget(self.status_dot)

        # ── Role buttons ──────────────────────────────────────────────
        role_row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None, height=H_BTN, spacing=12,
        )

        self.master_btn = SwampButton(
            text="Be Master  ★",
            color=C_MASTER,
            height=H_BTN,
        )
        self.master_btn.bind(on_press=self._on_master)
        role_row.add_widget(self.master_btn)

        self.node_btn = SwampButton(
            text="Join as Node  ⊙",
            color=C_NODE,
            height=H_BTN,
        )
        self.node_btn.bind(on_press=self._on_node)
        role_row.add_widget(self.node_btn)

        root.add_widget(role_row)

        # ── Stop button ───────────────────────────────────────────────
        self.stop_btn = SwampButton(
            text="Stop",
            color=T_DIM,
            height=H_BTN_SM,
        )
        self.stop_btn.bind(on_press=self._on_stop)
        self.stop_btn.disabled = True
        root.add_widget(self.stop_btn)

        # ── Status label ──────────────────────────────────────────────
        self.status_lbl = Label(
            text="Idle · choose a role above",
            font_size=FS_SM, color=T_DIM,
            size_hint_y=None, height=32,
            halign="center",
        )
        self.status_lbl.bind(size=lambda w, s: setattr(w, "text_size", (s[0], None)))
        root.add_widget(self.status_lbl)

        root.add_widget(Label(size_hint_y=0.1))

        # ── Role info panel ───────────────────────────────────────────
        info = BoxLayout(
            orientation="vertical",
            size_hint_y=None, height=64, spacing=2,
            padding=(SPACE_MD, SPACE_SM),
        )
        with info.canvas.before:
            Color(*BG_SURFACE)
            info._bg = RoundedRectangle(pos=info.pos, size=info.size, radius=RADIUS_MD)
        info.bind(pos=lambda w, p: setattr(w._bg, "pos", p),
                  size=lambda w, s: setattr(w._bg, "size", s))
        info.add_widget(Label(
            text="[b]Master[/b] = hub · holds shared state · relays messages",
            markup=True, font_size="12sp", color=(0.95, 0.75, 0.3, 1),
        ))
        info.add_widget(Label(
            text="[b]Node[/b]  = traveller · syncs with master · works offline too",
            markup=True, font_size="12sp", color=(0.4, 0.8, 1.0, 1),
        ))
        root.add_widget(info)

        root.add_widget(Label(size_hint_y=None, height=SPACE_SM))

        # ── Nav row ───────────────────────────────────────────────────
        nav = BoxLayout(
            orientation="horizontal",
            size_hint_y=None, height=H_NAV, spacing=SPACE_SM,
        )
        for label, sname in [
            ("Devices", "devices"),
            ("QR Pair", "qr"),
            ("Chat", "chat"),
            ("Files", "files"),
            ("Sync", "sync"),
        ]:
            btn = SwampButton(
                text=label,
                color=BG_RAISED,
                height=H_NAV,
            )
            btn.screen_name = sname
            btn.bind(on_press=lambda b, sn=sname: (
                setattr(self.manager, "current", sn) if self.manager else None
            ))
            nav.add_widget(btn)
        root.add_widget(nav)

        self.add_widget(root)

    def _label(self, text):
        lbl = Label(
            text=text, font_size=FS_SM, color=T_SECONDARY,
            size_hint_y=None, height=24, halign="left",
        )
        lbl.bind(size=lambda w, s: setattr(w, "text_size", (s[0], None)))
        return lbl

    def _upd_bg(self, *_):
        self._bg.pos = self.pos
        self._bg.size = self.size

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _on_master(self, _btn):
        if not self.app_ref or self._active_role != "idle":
            return
        name = self.name_input.text.strip() or "SwampDevice"
        self.app_ref.set_device_name(name)
        self.app_ref.start_as_master()
        self._set_active("master")

    def _on_node(self, _btn):
        if not self.app_ref or self._active_role != "idle":
            return
        name = self.name_input.text.strip() or "SwampDevice"
        self.app_ref.set_device_name(name)
        self.app_ref.start_as_node()
        self._set_active("node")

    def _on_stop(self, _btn):
        if self.app_ref:
            self.app_ref.stop_all()
        self._set_active("idle")

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def set_status_dot(self, text: str, color):
        """Update the StatusDot widget."""
        Clock.schedule_once(lambda dt: self.status_dot.set_status(text, color))

    def _set_active(self, role: str):
        self._active_role = role
        idle = role == "idle"
        self.master_btn.disabled = not idle
        self.node_btn.disabled = not idle
        self.name_input.disabled = not idle
        self.stop_btn.disabled = idle

        if role == "master":
            self.role_lbl.text = "Role: Master  ★"
            self.role_lbl.color = C_MASTER
            self.stop_btn.btn_color = C_DANGER
            self.set_status_dot("Master", C_MASTER)
        elif role == "node":
            self.role_lbl.text = "Role: Node  ⊙"
            self.role_lbl.color = C_NODE
            self.stop_btn.btn_color = C_DANGER
            self.set_status_dot("Node", C_NODE)
        else:
            self.role_lbl.text = "Choose a role to start"
            self.role_lbl.color = T_DIM
            self.stop_btn.btn_color = T_DIM
            self.set_status_dot("Idle", T_DIM)

    # Called by SwampApp from async context via Clock
    def set_status(self, running: bool, role: str, text: str = ""):
        """Update status label; role can be 'master', 'node', or 'idle'."""
        if role in ("master", "node"):
            self._set_active(role)
        elif not running:
            self._set_active("idle")
        self.status_lbl.text = text or ("Running" if running else "Idle")
        self.status_lbl.color = (
            C_MASTER if role == "master" else
            C_NODE   if role == "node"   else
            T_DIM
        )
