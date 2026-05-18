"""
chat.py — ChatScreen: real-time text chat with a connected peer.
"""

import logging
import time

from kivy.clock import Clock
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.graphics import Color, Rectangle, RoundedRectangle

from src.ui.theme import (
    BG_BASE, BG_SURFACE, BG_RAISED, BG_INPUT,
    C_GREEN, C_SUCCESS,
    T_PRIMARY, T_SECONDARY, T_DIM,
    FS_XS, FS_SM, FS_MD,
    RADIUS_MD,
    H_INPUT,
    SPACE_SM, SPACE_MD,
)
from src.ui.widgets import SwampHeader, SwampButton, EmptyState

logger = logging.getLogger(__name__)


class ChatBubble(BoxLayout):
    """A single chat message bubble."""

    def __init__(self, text: str, sender: str, is_self: bool, timestamp: float, **kwargs):
        super().__init__(
            orientation="vertical",
            size_hint_y=None,
            padding=(8, 4),
            **kwargs,
        )
        self.is_self = is_self

        import datetime
        ts_str = datetime.datetime.fromtimestamp(timestamp).strftime("%H:%M")

        outer = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            spacing=0,
        )

        if is_self:
            outer.add_widget(Label(size_hint_x=0.2))

        bubble_bg_color = C_SUCCESS if is_self else BG_RAISED

        bubble = BoxLayout(
            orientation="vertical",
            size_hint_x=0.75,
            padding=(10, 8),
            spacing=2,
        )
        with bubble.canvas.before:
            Color(*bubble_bg_color)
            bubble._bg = RoundedRectangle(pos=bubble.pos, size=bubble.size, radius=RADIUS_MD)
        bubble.bind(pos=lambda w, _: setattr(w._bg, "pos", w.pos))
        bubble.bind(size=lambda w, _: setattr(w._bg, "size", w.size))

        sender_lbl = Label(
            text=f"[b]{sender}[/b]",
            markup=True,
            font_size=FS_XS,
            color=(0.75, 0.95, 0.85, 1) if is_self else (0.6, 0.75, 0.9, 1),
            size_hint_y=None,
            height=18,
            halign="left",
        )
        sender_lbl.bind(size=lambda w, s: setattr(w, "text_size", (s[0], None)))

        msg_lbl = Label(
            text=text,
            font_size=FS_MD,
            color=T_PRIMARY,
            size_hint_y=None,
            halign="left",
            valign="top",
        )
        msg_lbl.bind(
            width=lambda w, v: setattr(w, "text_size", (v, None))
        )
        msg_lbl.bind(texture_size=lambda w, s: setattr(w, "height", s[1]))

        time_lbl = Label(
            text=ts_str,
            font_size="10sp",
            color=T_DIM,
            size_hint_y=None,
            height=16,
            halign="right",
        )
        time_lbl.bind(size=lambda w, s: setattr(w, "text_size", (s[0], None)))

        bubble.add_widget(sender_lbl)
        bubble.add_widget(msg_lbl)
        bubble.add_widget(time_lbl)

        def _update_bubble_height(*_):
            bubble.height = sender_lbl.height + msg_lbl.height + time_lbl.height + 24
            outer.height = bubble.height + 8
            self.height = outer.height + 8

        sender_lbl.bind(height=_update_bubble_height)
        msg_lbl.bind(height=_update_bubble_height)
        time_lbl.bind(height=_update_bubble_height)

        outer.add_widget(bubble)

        if not is_self:
            outer.add_widget(Label(size_hint_x=0.2))

        outer.height = 60
        self.height = 68

        self.add_widget(outer)


class ChatScreen(Screen):
    """
    Full-screen chat with a connected peer.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app_ref = None
        self.peer_name = "Peer"
        self._has_messages = False
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        with self.canvas.before:
            Color(*BG_BASE)
            self._bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._upd_bg, size=self._upd_bg)

        root = BoxLayout(orientation="vertical", spacing=0)

        # Header
        self.header = SwampHeader(title="Chat", back_screen="devices")
        root.add_widget(self.header)

        # Message area: empty state + scroll stacked
        self._msg_area = BoxLayout(orientation="vertical")

        self._empty_state = EmptyState(
            icon="✉",
            title="No messages yet",
            subtitle="Connect to a peer to start chatting",
        )
        self._msg_area.add_widget(self._empty_state)

        scroll = ScrollView(bar_width=4, do_scroll_x=False)
        self._scroll = scroll

        self.msg_list = BoxLayout(
            orientation="vertical",
            spacing=4,
            padding=(8, 8),
            size_hint_y=None,
        )
        self.msg_list.bind(minimum_height=self.msg_list.setter("height"))
        scroll.add_widget(self.msg_list)
        scroll.opacity = 0
        scroll.disabled = True
        self._msg_area.add_widget(scroll)

        root.add_widget(self._msg_area)

        # Input row
        input_row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=H_INPUT + SPACE_MD,
            padding=(SPACE_SM, SPACE_SM),
            spacing=SPACE_SM,
        )
        with input_row.canvas.before:
            Color(*BG_RAISED)
            input_row._bg = Rectangle(pos=input_row.pos, size=input_row.size)
        input_row.bind(pos=lambda w, _: setattr(w._bg, "pos", w.pos))
        input_row.bind(size=lambda w, _: setattr(w._bg, "size", w.size))

        self.msg_input = TextInput(
            hint_text="Type a message…",
            multiline=False,
            size_hint_y=None,
            height=H_INPUT,
            font_size=FS_MD,
            background_color=BG_INPUT,
            foreground_color=T_PRIMARY,
            cursor_color=C_GREEN,
        )
        self.msg_input.bind(on_text_validate=self._on_send)
        input_row.add_widget(self.msg_input)

        self._send_btn = SwampButton(
            text="↑",
            color=C_GREEN,
            height=H_INPUT,
        )
        self._send_btn.size_hint = (None, None)
        self._send_btn.width = 52
        self._send_btn.bind(on_press=self._on_send)
        input_row.add_widget(self._send_btn)
        root.add_widget(input_row)

        self.add_widget(root)

    def on_enter(self, *args):
        self.header.set_manager(self.manager)

    def _upd_bg(self, *_):
        self._bg.pos = self.pos
        self._bg.size = self.size

    def _go(self, screen_name):
        if self.manager:
            self.manager.current = screen_name

    # ------------------------------------------------------------------
    # Peer management
    # ------------------------------------------------------------------

    def set_peer(self, peer_name: str):
        """Update the active chat peer."""
        self.peer_name = peer_name
        self.header.title = f"Chat — {peer_name}"

    # ------------------------------------------------------------------
    # Message handling
    # ------------------------------------------------------------------

    def _on_send(self, *_):
        text = self.msg_input.text.strip()
        if not text:
            return
        self.msg_input.text = ""

        if self.app_ref:
            self.app_ref.send_chat_message(text, self.peer_name)

        self.add_message(text, self.app_ref.device_name if self.app_ref else "Me", True, time.time())

    def add_message(self, text: str, sender: str, is_self: bool, timestamp: float):
        """Add a message bubble to the list (safe to call from any thread)."""
        Clock.schedule_once(lambda dt: self._add_message_ui(text, sender, is_self, timestamp))

    def _add_message_ui(self, text: str, sender: str, is_self: bool, timestamp: float):
        if not self._has_messages:
            self._has_messages = True
            self._empty_state.opacity = 0
            self._empty_state.disabled = True
            self._scroll.opacity = 1
            self._scroll.disabled = False

        bubble = ChatBubble(text=text, sender=sender, is_self=is_self, timestamp=timestamp)
        self.msg_list.add_widget(bubble)
        Clock.schedule_once(lambda dt: self._scroll_to_bottom(), 0.05)

    def _scroll_to_bottom(self):
        self._scroll.scroll_y = 0
