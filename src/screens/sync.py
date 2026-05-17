"""
sync.py — SyncScreen: sync contacts/clipboard and start/stop screen sharing.
"""

import io
import json
import logging
import threading
import time

from kivy.clock import Clock
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.image import Image as KivyImage
from kivy.graphics import Color, Rectangle, Texture
from kivy.graphics.texture import Texture as KivyTexture

logger = logging.getLogger(__name__)


class SyncScreen(Screen):
    """
    Screen for data sync (contacts / clipboard) and screen sharing.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app_ref = None
        self._screen_sharing = False
        self._capture_session = None
        self._frame_index = 0

        # For displaying received screen frames
        self._rx_texture = None
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        with self.canvas.before:
            Color(0.08, 0.10, 0.12, 1)
            self._bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._upd_bg, size=self._upd_bg)

        root = BoxLayout(orientation="vertical", padding=(16, 12), spacing=10)

        # Header
        header = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=56,
            spacing=12,
        )
        back_btn = Button(
            text="← Home",
            size_hint=(None, 1),
            width=100,
            font_size="14sp",
            background_color=(0.2, 0.24, 0.28, 1),
            background_normal="",
        )
        back_btn.bind(on_press=lambda _: self._go("home"))
        header.add_widget(back_btn)
        header.add_widget(Label(
            text="[b]Sync & Share[/b]",
            markup=True,
            font_size="20sp",
            color=(1, 1, 1, 1),
        ))
        root.add_widget(header)

        # Peer label
        self.peer_lbl = Label(
            text="No peer connected",
            font_size="13sp",
            color=(0.55, 0.55, 0.55, 1),
            size_hint_y=None,
            height=28,
            halign="center",
        )
        self.peer_lbl.bind(size=lambda w, s: setattr(w, "text_size", (s[0], None)))
        root.add_widget(self.peer_lbl)

        # ── Data Sync section ──────────────────────────────────────────
        root.add_widget(self._section_label("Data Sync"))

        sync_row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=52,
            spacing=10,
        )
        contacts_btn = Button(
            text="Sync Contacts",
            font_size="14sp",
            background_color=(0.18, 0.55, 0.85, 1),
            background_normal="",
        )
        contacts_btn.bind(on_press=self._on_sync_contacts)
        sync_row.add_widget(contacts_btn)

        clipboard_btn = Button(
            text="Share Clipboard",
            font_size="14sp",
            background_color=(0.55, 0.35, 0.85, 1),
            background_normal="",
        )
        clipboard_btn.bind(on_press=self._on_share_clipboard)
        sync_row.add_widget(clipboard_btn)
        root.add_widget(sync_row)

        self.sync_status_lbl = Label(
            text="",
            font_size="12sp",
            color=(0.6, 0.6, 0.6, 1),
            size_hint_y=None,
            height=24,
            halign="center",
        )
        self.sync_status_lbl.bind(size=lambda w, s: setattr(w, "text_size", (s[0], None)))
        root.add_widget(self.sync_status_lbl)

        # Received data display
        root.add_widget(self._section_label("Received Data"))
        scroll = ScrollView(size_hint_y=0.25, bar_width=4)
        self.received_display = TextInput(
            hint_text="Received sync data will appear here…",
            readonly=True,
            multiline=True,
            font_size="13sp",
            background_color=(0.12, 0.15, 0.18, 1),
            foreground_color=(0.9, 0.9, 0.9, 1),
        )
        scroll.add_widget(self.received_display)
        root.add_widget(scroll)

        # ── Screen Share section ───────────────────────────────────────
        root.add_widget(self._section_label("Screen Share"))

        share_row = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=52,
            spacing=10,
        )
        self.screen_share_btn = Button(
            text="Start Screen Share",
            font_size="14sp",
            background_color=(0.2, 0.75, 0.55, 1),
            background_normal="",
        )
        self.screen_share_btn.bind(on_press=self._on_toggle_screen_share)
        share_row.add_widget(self.screen_share_btn)
        root.add_widget(share_row)

        self.share_status_lbl = Label(
            text="Screen sharing: off",
            font_size="12sp",
            color=(0.55, 0.55, 0.55, 1),
            size_hint_y=None,
            height=24,
            halign="center",
        )
        self.share_status_lbl.bind(size=lambda w, s: setattr(w, "text_size", (s[0], None)))
        root.add_widget(self.share_status_lbl)

        # Received screen frame display
        root.add_widget(self._section_label("Received Screen"))
        self.screen_image = KivyImage(
            size_hint_y=None,
            height=180,
            allow_stretch=True,
            keep_ratio=True,
        )
        with self.screen_image.canvas.before:
            Color(0.08, 0.1, 0.12, 1)
            Rectangle(pos=self.screen_image.pos, size=self.screen_image.size)
        root.add_widget(self.screen_image)

        self.add_widget(root)

    def _section_label(self, text: str) -> Label:
        lbl = Label(
            text=f"[b]{text}[/b]",
            markup=True,
            font_size="15sp",
            color=(0.7, 0.75, 0.8, 1),
            size_hint_y=None,
            height=30,
            halign="left",
        )
        lbl.bind(size=lambda w, s: setattr(w, "text_size", (s[0], None)))
        return lbl

    def _upd_bg(self, *_):
        self._bg.pos = self.pos
        self._bg.size = self.size

    def _go(self, screen_name):
        if self.manager:
            self.manager.current = screen_name

    # ------------------------------------------------------------------
    # Peer
    # ------------------------------------------------------------------

    def set_peer(self, peer_name: str):
        Clock.schedule_once(lambda dt: setattr(
            self.peer_lbl, "text",
            f"Connected to: [b]{peer_name}[/b]" if peer_name else "No peer connected",
        ))
        if peer_name:
            self.peer_lbl.markup = True

    # ------------------------------------------------------------------
    # Contacts sync
    # ------------------------------------------------------------------

    def _on_sync_contacts(self, *_):
        if not self.app_ref:
            self.sync_status_lbl.text = "App not ready."
            return
        self.sync_status_lbl.text = "Reading contacts…"
        threading.Thread(target=self._sync_contacts_thread, daemon=True).start()

    def _sync_contacts_thread(self):
        from src.utils.android_utils import read_contacts
        contacts = read_contacts()
        payload = json.dumps(contacts, ensure_ascii=False)
        Clock.schedule_once(lambda dt: self._do_send_sync("contacts", payload))

    def _do_send_sync(self, data_type: str, payload: str):
        if self.app_ref:
            self.app_ref.send_sync_data(data_type, payload)
            self.sync_status_lbl.text = f"Contacts sent ({len(json.loads(payload))} entries)."
        else:
            self.sync_status_lbl.text = "Not connected."

    # ------------------------------------------------------------------
    # Clipboard sync
    # ------------------------------------------------------------------

    def _on_share_clipboard(self, *_):
        if not self.app_ref:
            self.sync_status_lbl.text = "App not ready."
            return
        from src.utils.android_utils import get_clipboard_text
        text = get_clipboard_text()
        if not text:
            self.sync_status_lbl.text = "Clipboard is empty."
            return
        self.app_ref.send_sync_data("clipboard", text)
        self.sync_status_lbl.text = f"Clipboard shared ({len(text)} chars)."

    # ------------------------------------------------------------------
    # Received sync data
    # ------------------------------------------------------------------

    def on_sync_data_received(self, data_type: str, payload: str):
        """Called from the network handler (any thread)."""
        Clock.schedule_once(lambda dt: self._show_received_data(data_type, payload))

    def _show_received_data(self, data_type: str, payload: str):
        if data_type == "contacts":
            try:
                contacts = json.loads(payload)
                lines = [f"{c.get('name','')} — {c.get('phone','')}" for c in contacts]
                text = f"=== Contacts ({len(contacts)}) ===\n" + "\n".join(lines)
            except Exception:
                text = payload
        elif data_type == "clipboard":
            text = f"=== Clipboard ===\n{payload}"
            from src.utils.android_utils import set_clipboard_text
            try:
                set_clipboard_text(payload)
            except Exception:
                pass
        else:
            text = f"=== {data_type} ===\n{payload}"

        self.received_display.text = text

    # ------------------------------------------------------------------
    # Screen sharing
    # ------------------------------------------------------------------

    def _on_toggle_screen_share(self, *_):
        if not self._screen_sharing:
            self._start_screen_share()
        else:
            self._stop_screen_share()

    def _start_screen_share(self):
        if not self.app_ref:
            self.share_status_lbl.text = "App not ready."
            return

        from src.utils.android_utils import ScreenCaptureSession
        self._capture_session = ScreenCaptureSession()
        self._frame_index = 0
        self._capture_session.start(
            frame_callback=self._on_capture_frame,
            fps=5,
        )
        self._screen_sharing = True
        self.screen_share_btn.text = "Stop Screen Share"
        self.screen_share_btn.background_color = (0.85, 0.3, 0.2, 1)
        self.share_status_lbl.text = "Screen sharing: on"
        logger.info("Screen share started")

    def _stop_screen_share(self):
        if self._capture_session:
            self._capture_session.stop()
            self._capture_session = None
        self._screen_sharing = False
        self.screen_share_btn.text = "Start Screen Share"
        self.screen_share_btn.background_color = (0.2, 0.75, 0.55, 1)
        self.share_status_lbl.text = "Screen sharing: off"
        logger.info("Screen share stopped")

    def _on_capture_frame(self, jpeg_bytes: bytes, width: int, height: int):
        """Called from the capture thread; send frame via network."""
        if not self.app_ref or not jpeg_bytes:
            return
        idx = self._frame_index
        self._frame_index += 1
        self.app_ref.send_screen_frame(jpeg_bytes, idx, width, height)

    # ------------------------------------------------------------------
    # Received screen frame
    # ------------------------------------------------------------------

    def on_screen_frame_received(self, jpeg_bytes: bytes, width: int, height: int):
        """Called from network thread when a SCREEN_FRAME arrives."""
        Clock.schedule_once(lambda dt: self._display_frame(jpeg_bytes, width, height))

    def _display_frame(self, jpeg_bytes: bytes, width: int, height: int):
        """Decode JPEG and blit to Kivy Image widget."""
        try:
            from PIL import Image as PILImage  # type: ignore
            img = PILImage.open(io.BytesIO(jpeg_bytes)).convert("RGB")
            w, h = img.size
            raw = img.tobytes()
            texture = KivyTexture.create(size=(w, h), colorfmt="rgb")
            texture.blit_buffer(raw, colorfmt="rgb", bufferfmt="ubyte")
            texture.flip_vertical()
            self.screen_image.texture = texture
            self.share_status_lbl.text = f"Receiving: {w}×{h} frame #{self._frame_index}"
            self._frame_index += 1
        except Exception as e:
            logger.error("_display_frame: %s", e)
