"""
qr_screen.py — QR-code pairing screen.

Two modes, toggled by header buttons:
  • Show  (default) — display our own QR code for another device to scan.
  • Scan            — use the camera to scan a peer's QR code.

Both modes live in one Screen; only one layout is visible at a time
(opacity + disabled).
"""

import logging
import os

from kivy.clock import Clock
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.textinput import TextInput
from kivy.uix.popup import Popup
from kivy.graphics import Color, Rectangle

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Palette (matches rest of app)                                               #
# --------------------------------------------------------------------------- #
C_BG     = (0.08, 0.10, 0.12, 1)
C_GREEN  = (0.20, 0.85, 0.55, 1)
C_MASTER = (0.95, 0.60, 0.10, 1)
C_NODE   = (0.15, 0.65, 0.85, 1)
C_NAV    = (0.18, 0.22, 0.26, 1)
C_PANEL  = (0.13, 0.16, 0.20, 1)
C_DIM    = (0.50, 0.50, 0.50, 1)

# Camera is an optional, platform-dependent widget
try:
    from kivy.uix.camera import Camera
    CAMERA_AVAILABLE = True
except Exception:
    CAMERA_AVAILABLE = False

# QR utilities — guarded in their own module
try:
    from src.utils.qr_utils import (
        generate_qr_payload,
        parse_qr_payload,
        generate_qr_image,
        pil_to_kivy_texture,
        decode_qr_from_pil,
        QRCODE_AVAILABLE,
        PYZBAR_AVAILABLE,
        PIL_AVAILABLE,
    )
    QR_UTILS_AVAILABLE = True
except Exception:
    QR_UTILS_AVAILABLE = False
    QRCODE_AVAILABLE = False
    PYZBAR_AVAILABLE = False
    PIL_AVAILABLE = False


# --------------------------------------------------------------------------- #
# Helper: small nav button                                                    #
# --------------------------------------------------------------------------- #

def _nav_btn(text, width=110, color=C_NAV):
    return Button(
        text=text,
        size_hint=(None, 1), width=width,
        font_size="14sp",
        background_color=color,
        background_normal="",
    )


# --------------------------------------------------------------------------- #
# QRScreen                                                                    #
# --------------------------------------------------------------------------- #

class QRScreen(Screen):
    """QR code generation + scanning screen."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app_ref = None
        self._scan_event = None      # Clock event for frame polling
        self._camera_widget = None   # Camera instance (if available)
        self._build_ui()

    # ---------------------------------------------------------------------- #
    # UI construction                                                         #
    # ---------------------------------------------------------------------- #

    def _build_ui(self):
        with self.canvas.before:
            Color(*C_BG)
            self._bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._upd_bg, size=self._upd_bg)

        self._root = BoxLayout(orientation="vertical", padding=(16, 12), spacing=0)
        self.add_widget(self._root)

        self._show_layout = self._build_show_layout()
        self._scan_layout = self._build_scan_layout()

        self._root.add_widget(self._show_layout)
        self._root.add_widget(self._scan_layout)

        # Start in "show" mode
        self._set_mode("show")

    # ── Show-mode layout ─────────────────────────────────────────────────── #

    def _build_show_layout(self) -> BoxLayout:
        layout = BoxLayout(orientation="vertical", spacing=14)

        # Header
        header = BoxLayout(orientation="horizontal", size_hint_y=None, height=56, spacing=12)
        back_btn = _nav_btn("← Back")
        back_btn.bind(on_press=lambda _: self._go("home"))
        header.add_widget(back_btn)

        header.add_widget(Label(
            text="[b]QR Pair[/b]", markup=True,
            font_size="20sp", color=(1, 1, 1, 1),
        ))

        scan_btn = _nav_btn("Scan", color=(0.18, 0.55, 0.85, 1))
        scan_btn.bind(on_press=lambda _: self._set_mode("scan"))
        header.add_widget(scan_btn)

        layout.add_widget(header)

        # QR image widget
        self.qr_image = Image(
            size_hint=(None, None),
            size=(300, 300),
            pos_hint={"center_x": 0.5},
        )
        layout.add_widget(self.qr_image)

        # Device info labels
        self.show_name_lbl = Label(
            text="",
            markup=True, font_size="22sp",
            color=C_GREEN,
            size_hint_y=None, height=38,
            halign="center",
        )
        self.show_name_lbl.bind(size=lambda w, s: setattr(w, "text_size", (s[0], None)))
        layout.add_widget(self.show_name_lbl)

        self.show_role_lbl = Label(
            text="",
            font_size="15sp",
            color=C_DIM,
            size_hint_y=None, height=28,
            halign="center",
        )
        self.show_role_lbl.bind(size=lambda w, s: setattr(w, "text_size", (s[0], None)))
        layout.add_widget(self.show_role_lbl)

        self.show_addr_lbl = Label(
            text="",
            font_size="13sp",
            color=C_DIM,
            size_hint_y=None, height=24,
            halign="center",
        )
        self.show_addr_lbl.bind(size=lambda w, s: setattr(w, "text_size", (s[0], None)))
        layout.add_widget(self.show_addr_lbl)

        layout.add_widget(Label(
            text="Show this to another device to pair instantly",
            font_size="13sp", color=C_DIM,
            size_hint_y=None, height=28,
            halign="center",
        ))

        # Spacer
        layout.add_widget(Label())

        return layout

    # ── Scan-mode layout ─────────────────────────────────────────────────── #

    def _build_scan_layout(self) -> BoxLayout:
        layout = BoxLayout(orientation="vertical", spacing=12)

        # Header
        header = BoxLayout(orientation="horizontal", size_hint_y=None, height=56, spacing=12)
        back_btn = _nav_btn("← Back")
        back_btn.bind(on_press=lambda _: self._go("home"))
        header.add_widget(back_btn)

        header.add_widget(Label(
            text="[b]Scan QR[/b]", markup=True,
            font_size="20sp", color=(1, 1, 1, 1),
        ))

        show_btn = _nav_btn("Show Mine", color=(0.18, 0.55, 0.85, 1))
        show_btn.bind(on_press=lambda _: self._set_mode("show"))
        header.add_widget(show_btn)

        layout.add_widget(header)

        # Camera area — populated lazily in _start_camera()
        self._camera_container = BoxLayout(
            orientation="vertical",
            spacing=8,
        )
        layout.add_widget(self._camera_container)

        self.scan_status_lbl = Label(
            text="Pointing camera at a Swamp QR code…",
            font_size="13sp", color=C_DIM,
            size_hint_y=None, height=32,
            halign="center",
        )
        self.scan_status_lbl.bind(size=lambda w, s: setattr(w, "text_size", (s[0], None)))
        layout.add_widget(self.scan_status_lbl)

        return layout

    # ---------------------------------------------------------------------- #
    # Mode switching                                                          #
    # ---------------------------------------------------------------------- #

    def _set_mode(self, mode: str):
        """Switch between 'show' and 'scan' modes."""
        if mode == "show":
            self._show_layout.opacity = 1
            self._show_layout.disabled = False
            self._scan_layout.opacity = 0
            self._scan_layout.disabled = True
            self._stop_scan()
        else:
            self._show_layout.opacity = 0
            self._show_layout.disabled = True
            self._scan_layout.opacity = 1
            self._scan_layout.disabled = False
            Clock.schedule_once(lambda dt: self._start_camera(), 0.1)

    # ---------------------------------------------------------------------- #
    # Screen lifecycle                                                        #
    # ---------------------------------------------------------------------- #

    def on_enter(self, *args):
        """Regenerate our QR code every time this screen is shown."""
        Clock.schedule_once(lambda dt: self._refresh_qr(), 0)

    def on_leave(self, *args):
        """Stop the camera and scan timer when navigating away."""
        self._stop_scan()

    # ---------------------------------------------------------------------- #
    # Show-mode: QR generation                                               #
    # ---------------------------------------------------------------------- #

    def _refresh_qr(self):
        if not self.app_ref:
            return
        try:
            info = self.app_ref.get_qr_info()
        except Exception as exc:
            logger.warning("get_qr_info failed: %s", exc)
            return

        name = info.get("name", "")
        ip   = info.get("ip", "")
        port = info.get("port", 54321)
        role = info.get("role", "node")
        nid  = info.get("node_id", "")

        # Labels
        self.show_name_lbl.text = f"[b]{name}[/b]"
        self.show_addr_lbl.text = f"{ip}:{port}"
        if role == "master":
            self.show_role_lbl.text = "★  Master"
            self.show_role_lbl.color = C_MASTER
        else:
            self.show_role_lbl.text = "⊙  Node"
            self.show_role_lbl.color = C_NODE

        # QR image
        if QR_UTILS_AVAILABLE and QRCODE_AVAILABLE and PIL_AVAILABLE:
            payload = generate_qr_payload(name, ip, port, role, nid)
            pil_img = generate_qr_image(payload, size=300)
            if pil_img is not None:
                try:
                    texture = pil_to_kivy_texture(pil_img)
                    self.qr_image.texture = texture
                except Exception as exc:
                    logger.warning("pil_to_kivy_texture failed: %s", exc)
            else:
                self.show_name_lbl.text = "[b]QR unavailable[/b]"
        else:
            self.show_name_lbl.text = f"[b]{name}[/b]"
            self.show_addr_lbl.text = f"{ip}:{port}  (install qrcode[pil] for QR image)"

    # ---------------------------------------------------------------------- #
    # Scan-mode: camera + decode                                              #
    # ---------------------------------------------------------------------- #

    def _start_camera(self):
        """Instantiate the camera widget or fall back to manual entry."""
        # Clear any previous content
        self._camera_container.clear_widgets()
        self._camera_widget = None

        if CAMERA_AVAILABLE:
            try:
                cam = Camera(resolution=(640, 480), play=True)
                self._camera_widget = cam
                self._camera_container.add_widget(cam)
                self.scan_status_lbl.text = "Pointing camera at a Swamp QR code…"
                # Start polling
                self._scan_event = Clock.schedule_interval(self._scan_frame, 0.5)
                return
            except Exception as exc:
                logger.warning("Camera init failed: %s", exc)

        # Fallback: manual IP entry
        self._build_manual_entry()

    def _stop_scan(self):
        if self._scan_event is not None:
            self._scan_event.cancel()
            self._scan_event = None
        if self._camera_widget is not None:
            try:
                self._camera_widget.play = False
            except Exception:
                pass
            self._camera_widget = None

    def _scan_frame(self, dt):
        """Called every 0.5 s while the camera is active; tries to decode a QR."""
        if self._camera_widget is None:
            return

        if not PYZBAR_AVAILABLE or not PIL_AVAILABLE or not QR_UTILS_AVAILABLE:
            self._stop_scan()
            Clock.schedule_once(lambda _dt: self._build_manual_entry(), 0)
            return

        frame_path = "/tmp/swamp_frame.png"
        try:
            self._camera_widget.export_to_png(frame_path)
        except Exception as exc:
            logger.debug("export_to_png failed: %s", exc)
            return

        try:
            from PIL import Image as PILImage
            pil_img = PILImage.open(frame_path)
            decoded = decode_qr_from_pil(pil_img)
        except Exception as exc:
            logger.debug("Frame decode error: %s", exc)
            return

        if decoded:
            info = parse_qr_payload(decoded)
            if info:
                self._stop_scan()
                Clock.schedule_once(lambda _dt: self._on_scan_success(info), 0)

    def _on_scan_success(self, info: dict):
        """Show a confirmation popup after a successful scan."""
        self.scan_status_lbl.text = f"Found: {info.get('name', '?')}"

        role = info.get("role", "node")
        role_label = "★ Master" if role == "master" else "⊙ Node"
        role_color = C_MASTER if role == "master" else C_NODE

        content = BoxLayout(orientation="vertical", padding=20, spacing=14)
        content.add_widget(Label(
            text=f"[b]{info.get('name', '?')}[/b]",
            markup=True, font_size="22sp", color=C_GREEN,
            size_hint_y=None, height=38,
        ))
        content.add_widget(Label(
            text=role_label,
            font_size="16sp", color=role_color,
            size_hint_y=None, height=28,
        ))
        content.add_widget(Label(
            text=f"{info.get('ip', '')}:{info.get('port', '')}",
            font_size="14sp", color=C_DIM,
            size_hint_y=None, height=26,
        ))

        popup_ref = [None]  # mutable container so the closure can dismiss it

        connect_btn = Button(
            text="Connect",
            size_hint_y=None, height=50,
            font_size="16sp",
            background_color=C_GREEN,
            background_normal="",
        )

        def _do_connect(_btn):
            if popup_ref[0]:
                popup_ref[0].dismiss()
            if self.app_ref:
                self.app_ref.connect_from_qr(info)
            self._go("home")

        connect_btn.bind(on_press=_do_connect)
        content.add_widget(connect_btn)

        cancel_btn = Button(
            text="Cancel",
            size_hint_y=None, height=44,
            font_size="14sp",
            background_color=C_NAV,
            background_normal="",
        )
        cancel_btn.bind(on_press=lambda _: popup_ref[0].dismiss() if popup_ref[0] else None)
        content.add_widget(cancel_btn)

        popup = Popup(
            title="Pair with device?",
            content=content,
            size_hint=(0.85, None),
            height=340,
            background_color=(0.10, 0.13, 0.16, 1),
        )
        popup_ref[0] = popup
        popup.open()

    # ---------------------------------------------------------------------- #
    # Manual entry fallback (desktop / no camera / no pyzbar)                #
    # ---------------------------------------------------------------------- #

    def _build_manual_entry(self):
        self._camera_container.clear_widgets()

        self.scan_status_lbl.text = "Camera unavailable — enter IP manually"

        instruction = Label(
            text="Enter peer IP address",
            font_size="14sp", color=C_DIM,
            size_hint_y=None, height=30,
            halign="center",
        )
        instruction.bind(size=lambda w, s: setattr(w, "text_size", (s[0], None)))
        self._camera_container.add_widget(instruction)

        self._manual_ip = TextInput(
            hint_text="192.168.x.x",
            multiline=False,
            size_hint_y=None, height=48,
            font_size="16sp",
            background_color=C_PANEL,
            foreground_color=(1, 1, 1, 1),
            cursor_color=C_GREEN,
        )
        self._camera_container.add_widget(self._manual_ip)

        connect_btn = Button(
            text="Connect",
            size_hint_y=None, height=52,
            font_size="16sp",
            background_color=C_GREEN,
            background_normal="",
        )
        connect_btn.bind(on_press=self._on_manual_connect)
        self._camera_container.add_widget(connect_btn)

        # Push widgets to the top
        self._camera_container.add_widget(Label())

    def _on_manual_connect(self, _btn):
        if not self.app_ref:
            return
        ip = self._manual_ip.text.strip() if hasattr(self, "_manual_ip") else ""
        if not ip:
            self.scan_status_lbl.text = "Please enter an IP address"
            return
        info = {
            "name": ip,
            "ip": ip,
            "port": 54321,
            "role": "node",
            "node_id": ip,
        }
        self.app_ref.connect_from_qr(info)
        self._go("home")

    # ---------------------------------------------------------------------- #
    # Navigation helper                                                       #
    # ---------------------------------------------------------------------- #

    def _go(self, screen_name: str):
        if self.manager:
            self.manager.current = screen_name

    def _upd_bg(self, *_):
        self._bg.pos = self.pos
        self._bg.size = self.size
