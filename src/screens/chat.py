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
from kivy.uix.button import Button
from kivy.graphics import Color, Rectangle, RoundedRectangle

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

        # Time string
        import datetime
        ts_str = datetime.datetime.fromtimestamp(timestamp).strftime("%H:%M")

        outer = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            spacing=0,
        )

        # Push self messages to the right
        if is_self:
            outer.add_widget(Label(size_hint_x=0.2))

        bubble_bg_color = (0.2, 0.55, 0.35, 1) if is_self else (0.18, 0.22, 0.28, 1)

        bubble = BoxLayout(
            orientation="vertical",
            size_hint_x=0.75,
            padding=(10, 8),
            spacing=2,
        )
        with bubble.canvas.before:
            Color(*bubble_bg_color)
            bubble._bg = RoundedRectangle(pos=bubble.pos, size=bubble.size, radius=[10])
        bubble.bind(pos=lambda w, _: setattr(w._bg, "pos", w.pos))
        bubble.bind(size=lambda w, _: setattr(w._bg, "size", w.size))

        sender_lbl = Label(
            text=f"[b]{sender}[/b]",
            markup=True,
            font_size="11sp",
            color=(0.75, 0.95, 0.85, 1) if is_self else (0.6, 0.75, 0.9, 1),
            size_hint_y=None,
            height=18,
            halign="left",
        )
        sender_lbl.bind(size=lambda w, s: setattr(w, "text_size", (s[0], None)))

        msg_lbl = Label(
            text=text,
            font_size="15sp",
            color=(1, 1, 1, 1),
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
            color=(0.6, 0.6, 0.6, 1),
            size_hint_y=None,
            height=16,
            halign="right",
        )
        time_lbl.bind(size=lambda w, s: setattr(w, "text_size", (s[0], None)))

        bubble.add_widget(sender_lbl)
        bubble.add_widget(msg_lbl)
        bubble.add_widget(time_lbl)

        # Bind bubble height to content
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

        outer.height = 60  # default, updated above
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
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        with self.canvas.before:
            Color(0.08, 0.10, 0.12, 1)
            self._bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._upd_bg, size=self._upd_bg)

        root = BoxLayout(orientation="vertical", spacing=0)

        # Header
        header = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=56,
            padding=(8, 6),
            spacing=10,
        )
        with header.canvas.before:
            Color(0.10, 0.13, 0.16, 1)
            header._bg = Rectangle(pos=header.pos, size=header.size)
        header.bind(pos=lambda w, _: setattr(w._bg, "pos", w.pos))
        header.bind(size=lambda w, _: setattr(w._bg, "size", w.size))

        back_btn = Button(
            text="←",
            size_hint=(None, 1),
            width=50,
            font_size="20sp",
            background_color=(0.2, 0.24, 0.28, 1),
            background_normal="",
        )
        back_btn.bind(on_press=lambda _: self._go("devices"))
        header.add_widget(back_btn)

        self.header_lbl = Label(
            text=f"[b]Chat — {self.peer_name}[/b]",
            markup=True,
            font_size="18sp",
            color=(1, 1, 1, 1),
        )
        header.add_widget(self.header_lbl)
        root.add_widget(header)

        # Message list
        scroll = ScrollView(
            bar_width=4,
            do_scroll_x=False,
        )
        self._scroll = scroll

        self.msg_list = BoxLayout(
            orientation="vertical",
            spacing=4,
            padding=(8, 8),
            size_hint_y=None,
        )
        self.msg_list.bind(minimum_height=self.msg_list.setter("height"))
        scroll.add_widget(self.msg_list)
        root.add_widget(scroll)

        # Input row
        input_row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=56,
            padding=(8, 6),
            spacing=8,
        )
        with input_row.canvas.before:
            Color(0.10, 0.13, 0.16, 1)
            input_row._bg = Rectangle(pos=input_row.pos, size=input_row.size)
        input_row.bind(pos=lambda w, _: setattr(w._bg, "pos", w.pos))
        input_row.bind(size=lambda w, _: setattr(w._bg, "size", w.size))

        self.msg_input = TextInput(
            hint_text="Type a message…",
            multiline=False,
            size_hint_y=None,
            height=44,
            font_size="15sp",
            background_color=(0.15, 0.18, 0.22, 1),
            foreground_color=(1, 1, 1, 1),
            cursor_color=(0.2, 0.85, 0.6, 1),
        )
        self.msg_input.bind(on_text_validate=self._on_send)
        input_row.add_widget(self.msg_input)

        send_btn = Button(
            text="Send",
            size_hint=(None, None),
            width=80,
            height=44,
            font_size="15sp",
            background_color=(0.2, 0.75, 0.55, 1),
            background_normal="",
        )
        send_btn.bind(on_press=self._on_send)
        input_row.add_widget(send_btn)
        root.add_widget(input_row)

        self.add_widget(root)

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
        self.header_lbl.text = f"[b]Chat — {peer_name}[/b]"

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

        # Show in own UI immediately
        self.add_message(text, self.app_ref.device_name if self.app_ref else "Me", True, time.time())

    def add_message(self, text: str, sender: str, is_self: bool, timestamp: float):
        """Add a message bubble to the list (safe to call from any thread)."""
        Clock.schedule_once(lambda dt: self._add_message_ui(text, sender, is_self, timestamp))

    def _add_message_ui(self, text: str, sender: str, is_self: bool, timestamp: float):
        bubble = ChatBubble(text=text, sender=sender, is_self=is_self, timestamp=timestamp)
        self.msg_list.add_widget(bubble)
        # Scroll to bottom after layout
        Clock.schedule_once(lambda dt: self._scroll_to_bottom(), 0.05)

    def _scroll_to_bottom(self):
        self._scroll.scroll_y = 0
