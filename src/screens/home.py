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
from kivy.uix.button import Button
from kivy.graphics import Color, Rectangle, RoundedRectangle

logger = logging.getLogger(__name__)

# Palette
C_BG       = (0.08, 0.10, 0.12, 1)
C_MASTER   = (0.95, 0.60, 0.10, 1)   # amber  — the organiser
C_NODE     = (0.15, 0.65, 0.85, 1)   # sky-blue — the traveller
C_STOP     = (0.80, 0.25, 0.20, 1)   # red
C_PANEL    = (0.13, 0.16, 0.20, 1)
C_NAV      = (0.18, 0.22, 0.26, 1)
C_GREEN    = (0.20, 0.85, 0.55, 1)
C_DIM      = (0.50, 0.50, 0.50, 1)


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
            Color(*C_BG)
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
            font_size="14sp", color=C_DIM,
            size_hint_y=None, height=26,
        ))

        root.add_widget(Label(size_hint_y=None, height=8))

        # ── Device name ───────────────────────────────────────────────
        root.add_widget(self._label("Device Name"))
        self.name_input = TextInput(
            hint_text="Enter device name…",
            multiline=False,
            size_hint_y=None, height=48, font_size="16sp",
            background_color=C_PANEL,
            foreground_color=(1, 1, 1, 1),
            cursor_color=C_GREEN,
        )
        self.name_input.text = socket.gethostname().split(".")[0] or "SwampDevice"
        root.add_widget(self.name_input)

        # ── Role explanation ──────────────────────────────────────────
        self.role_lbl = Label(
            text="Choose a role to start",
            font_size="13sp", color=C_DIM,
            size_hint_y=None, height=24,
        )
        root.add_widget(self.role_lbl)

        # ── Role buttons ──────────────────────────────────────────────
        role_row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None, height=60, spacing=12,
        )

        self.master_btn = Button(
            text="Be Master  ★",
            font_size="16sp",
            background_color=C_MASTER,
            background_normal="",
        )
        self.master_btn.bind(on_press=self._on_master)
        role_row.add_widget(self.master_btn)

        self.node_btn = Button(
            text="Join as Node  ⊙",
            font_size="16sp",
            background_color=C_NODE,
            background_normal="",
        )
        self.node_btn.bind(on_press=self._on_node)
        role_row.add_widget(self.node_btn)

        root.add_widget(role_row)

        # ── Stop button ───────────────────────────────────────────────
        self.stop_btn = Button(
            text="Stop",
            size_hint_y=None, height=46, font_size="15sp",
            background_color=(0.25, 0.28, 0.32, 1),
            background_normal="",
            disabled=True,
        )
        self.stop_btn.bind(on_press=self._on_stop)
        root.add_widget(self.stop_btn)

        # ── Status ────────────────────────────────────────────────────
        self.status_lbl = Label(
            text="Idle · choose a role above",
            font_size="13sp", color=C_DIM,
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
        )
        with info.canvas.before:
            Color(*C_PANEL)
            info._bg = RoundedRectangle(pos=info.pos, size=info.size, radius=[10])
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

        root.add_widget(Label(size_hint_y=None, height=8))

        # ── Nav row ───────────────────────────────────────────────────
        nav = BoxLayout(
            orientation="horizontal",
            size_hint_y=None, height=52, spacing=8,
        )
        for label, sname in [
            ("Devices", "devices"),
            ("Chat", "chat"),
            ("Files", "files"),
            ("Sync", "sync"),
        ]:
            btn = Button(
                text=label, font_size="14sp",
                background_color=C_NAV, background_normal="",
            )
            btn.screen_name = sname
            btn.bind(on_press=lambda b: setattr(self.manager, "current", b.screen_name)
                     if self.manager else None)
            nav.add_widget(btn)
        root.add_widget(nav)

        self.add_widget(root)

    def _label(self, text):
        lbl = Label(
            text=text, font_size="13sp", color=(0.75, 0.75, 0.75, 1),
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

    def _set_active(self, role: str):
        self._active_role = role
        idle = role == "idle"
        self.master_btn.disabled = not idle
        self.node_btn.disabled = not idle
        self.name_input.disabled = not idle
        self.stop_btn.disabled = idle
        self.stop_btn.background_color = C_DIM if idle else C_STOP

        if role == "master":
            self.role_lbl.text = "Role: Master  ★"
            self.role_lbl.color = C_MASTER
        elif role == "node":
            self.role_lbl.text = "Role: Node  ⊙"
            self.role_lbl.color = C_NODE
        else:
            self.role_lbl.text = "Choose a role to start"
            self.role_lbl.color = C_DIM

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
            C_DIM
        )
