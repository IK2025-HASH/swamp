"""
files.py — FilesScreen: send/receive files with progress bar.
"""

import logging
import os
import time

from kivy.clock import Clock
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.progressbar import ProgressBar
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.utils import platform

from src.ui.theme import (
    BG_BASE, BG_SURFACE,
    C_GREEN, C_NODE,
    T_PRIMARY, T_SECONDARY, T_DIM,
    FS_XS, FS_SM, FS_MD, FS_LG,
    RADIUS_MD,
    H_BTN_SM, H_ROW,
    SPACE_SM, SPACE_MD,
)
from src.ui.widgets import SwampHeader, SwampButton, EmptyState

logger = logging.getLogger(__name__)


def _fmt_size(n: int) -> str:
    """Format bytes into a human-readable string."""
    if n < 1024:
        return f"{n:.0f} B"
    n /= 1024
    if n < 1024:
        return f"{n:.0f} KB"
    n /= 1024
    return f"{n:.1f} MB"


def _mime_icon(filename: str) -> str:
    """Return a Unicode icon based on file extension."""
    ext = os.path.splitext(filename)[1].lower()
    if ext in (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg"):
        return "🖼"
    if ext in (".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"):
        return "🎵"
    if ext in (".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm"):
        return "▶"
    if ext == ".pdf":
        return "📄"
    if ext in (".zip", ".tar", ".gz", ".bz2", ".7z", ".rar"):
        return "📦"
    return "📎"


def _pick_file_android(callback):
    """Launch Android file picker via Intent and return path via callback."""
    try:
        from jnius import autoclass  # type: ignore
        Intent = autoclass("android.content.Intent")
        intent = Intent(Intent.ACTION_GET_CONTENT)
        intent.setType("*/*")
        intent.addCategory(Intent.CATEGORY_OPENABLE)
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        PythonActivity.mActivity.startActivityForResult(intent, 2001)
        logger.info("Android file picker launched")
    except Exception as e:
        logger.error("_pick_file_android: %s", e)


def _pick_file_desktop(callback):
    """Use tkinter file dialog as a desktop fallback."""
    import threading

    def _run():
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            path = filedialog.askopenfilename()
            root.destroy()
            if path:
                Clock.schedule_once(lambda dt: callback(path))
        except Exception as e:
            logger.error("_pick_file_desktop: %s", e)

    threading.Thread(target=_run, daemon=True).start()


class FileRow(BoxLayout):
    """Row representing a received/sent file."""

    def __init__(self, filename: str, filesize: int, direction: str, path: str = "", **kwargs):
        super().__init__(
            orientation="horizontal",
            size_hint_y=None,
            height=H_ROW,
            padding=(12, 8),
            spacing=10,
            **kwargs,
        )
        with self.canvas.before:
            Color(*BG_SURFACE)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=RADIUS_MD)
        self.bind(pos=lambda w, _: setattr(w._bg, "pos", w.pos))
        self.bind(size=lambda w, _: setattr(w._bg, "size", w.size))

        # MIME icon + direction arrow
        icon_text = _mime_icon(filename)
        direction_arrow = "↓" if direction == "received" else "↑"
        icon_color = C_GREEN if direction == "received" else C_NODE

        icon_lbl = Label(
            text=f"{icon_text}\n{direction_arrow}",
            font_size="18sp",
            color=icon_color,
            size_hint=(None, 1),
            width=40,
            halign="center",
            valign="middle",
        )
        icon_lbl.bind(size=lambda w, s: setattr(w, "text_size", s))
        self.add_widget(icon_lbl)

        info = BoxLayout(orientation="vertical", spacing=2)
        name_lbl = Label(
            text=f"[b]{filename}[/b]",
            markup=True,
            font_size=FS_MD,
            color=T_PRIMARY,
            halign="left",
        )
        name_lbl.bind(size=lambda w, s: setattr(w, "text_size", (s[0], None)))

        size_str = _fmt_size(filesize)
        meta_lbl = Label(
            text=f"{size_str} · {direction}",
            font_size=FS_XS,
            color=T_DIM,
            halign="left",
        )
        meta_lbl.bind(size=lambda w, s: setattr(w, "text_size", (s[0], None)))

        info.add_widget(name_lbl)
        info.add_widget(meta_lbl)
        self.add_widget(info)


class FilesScreen(Screen):
    """
    Screen for sending and receiving files.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app_ref = None
        self._active_transfers = {}  # transfer_id -> {meta, progress_bar, bytes_received}
        self._file_count = 0
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        with self.canvas.before:
            Color(*BG_BASE)
            self._bg = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._upd_bg, size=self._upd_bg)

        root = BoxLayout(orientation="vertical", padding=(16, 12), spacing=SPACE_MD)

        # Header
        self.header = SwampHeader(title="Files", back_screen="home")
        root.add_widget(self.header)

        # Connected peer label
        self.peer_lbl = Label(
            text="No peer connected",
            font_size=FS_SM,
            color=T_DIM,
            size_hint_y=None,
            height=28,
            halign="center",
        )
        self.peer_lbl.bind(size=lambda w, s: setattr(w, "text_size", (s[0], None)))
        root.add_widget(self.peer_lbl)

        # Send section
        send_box = BoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=H_BTN_SM,
            spacing=SPACE_SM,
        )
        self._pick_btn = SwampButton(
            text="Pick File",
            color=C_NODE,
            height=H_BTN_SM,
        )
        self._pick_btn.size_hint = (None, 1)
        self._pick_btn.width = 120
        self._pick_btn.bind(on_press=self._on_pick_file)
        send_box.add_widget(self._pick_btn)

        self.selected_lbl = Label(
            text="No file selected",
            font_size=FS_SM,
            color=T_DIM,
            halign="left",
        )
        self.selected_lbl.bind(size=lambda w, s: setattr(w, "text_size", (s[0], None)))
        send_box.add_widget(self.selected_lbl)

        self.send_btn = SwampButton(
            text="Send",
            color=C_GREEN,
            height=H_BTN_SM,
        )
        self.send_btn.size_hint = (None, 1)
        self.send_btn.width = 90
        self.send_btn.bind(on_press=self._on_send_file)
        send_box.add_widget(self.send_btn)
        root.add_widget(send_box)

        # Send progress bar
        self.send_progress = ProgressBar(
            max=100,
            value=0,
            size_hint_y=None,
            height=10,
        )
        # Colour the progress bar green via canvas override
        with self.send_progress.canvas.before:
            Color(*C_GREEN)
            self._pb_rect = RoundedRectangle(
                pos=self.send_progress.pos,
                size=(0, self.send_progress.height),
                radius=[4],
            )
        self.send_progress.bind(pos=self._upd_pb, size=self._upd_pb, value=self._upd_pb)
        root.add_widget(self.send_progress)

        self.send_status_lbl = Label(
            text="",
            font_size="12sp",
            color=T_DIM,
            size_hint_y=None,
            height=22,
            halign="center",
        )
        self.send_status_lbl.bind(size=lambda w, s: setattr(w, "text_size", (s[0], None)))
        root.add_widget(self.send_status_lbl)

        # Received section header
        root.add_widget(Label(
            text="[b]Received Files[/b]",
            markup=True,
            font_size=FS_LG,
            color=T_SECONDARY,
            size_hint_y=None,
            height=32,
            halign="left",
        ))

        # Incoming progress area
        self.incoming_progress_box = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            spacing=4,
        )
        self.incoming_progress_box.bind(
            minimum_height=self.incoming_progress_box.setter("height")
        )
        root.add_widget(self.incoming_progress_box)

        # File list area: empty state + scroll
        self._list_area = BoxLayout(orientation="vertical")

        self._empty_state = EmptyState(
            icon="📎",
            title="No files yet",
            subtitle="Send or receive files from a connected peer",
        )
        self._list_area.add_widget(self._empty_state)

        scroll = ScrollView(bar_width=4)
        self.file_list = BoxLayout(
            orientation="vertical",
            spacing=SPACE_SM,
            padding=(0, 4),
            size_hint_y=None,
        )
        self.file_list.bind(minimum_height=self.file_list.setter("height"))
        scroll.add_widget(self.file_list)
        self._file_scroll = scroll
        scroll.opacity = 0
        scroll.disabled = True
        self._list_area.add_widget(scroll)

        root.add_widget(self._list_area)
        self.add_widget(root)

        self._selected_file = None

    def _upd_pb(self, *_):
        pb = self.send_progress
        if pb.max > 0:
            ratio = pb.value / pb.max
        else:
            ratio = 0
        self._pb_rect.pos = pb.pos
        self._pb_rect.size = (pb.width * ratio, pb.height)

    def on_enter(self, *args):
        self.header.set_manager(self.manager)

    def _upd_bg(self, *_):
        self._bg.pos = self.pos
        self._bg.size = self.size

    def _go(self, screen_name):
        if self.manager:
            self.manager.current = screen_name

    # ------------------------------------------------------------------
    # Peer status
    # ------------------------------------------------------------------

    def set_peer(self, peer_name: str):
        Clock.schedule_once(lambda dt: setattr(
            self.peer_lbl, "text",
            f"Connected to: [b]{peer_name}[/b]" if peer_name else "No peer connected",
        ))
        if peer_name:
            self.peer_lbl.markup = True

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    def _on_pick_file(self, *_):
        if platform == "android":
            _pick_file_android(self._file_selected)
        else:
            _pick_file_desktop(self._file_selected)

    def _file_selected(self, path: str):
        self._selected_file = path
        self.selected_lbl.text = os.path.basename(path)

    def _on_send_file(self, *_):
        if not self._selected_file:
            self.send_status_lbl.text = "No file selected."
            return
        if not self.app_ref:
            self.send_status_lbl.text = "App not ready."
            return
        self.send_progress.value = 0
        self.send_status_lbl.text = "Sending…"
        self.app_ref.send_file(self._selected_file, self._send_progress_cb)

    def _send_progress_cb(self, progress: float):
        """Called from asyncio thread; schedule UI update on main thread."""
        Clock.schedule_once(lambda dt: self._update_send_progress(progress))

    def _update_send_progress(self, progress: float):
        self.send_progress.value = int(progress * 100)
        if progress >= 1.0:
            self.send_status_lbl.text = "File sent successfully."
        else:
            self.send_status_lbl.text = f"Sending… {int(progress*100)}%"

    # ------------------------------------------------------------------
    # Receiving
    # ------------------------------------------------------------------

    def on_file_meta(self, transfer_id: str, filename: str, filesize: int):
        """Called when a FILE_META message arrives."""
        Clock.schedule_once(lambda dt: self._on_file_meta_ui(transfer_id, filename, filesize))

    def _on_file_meta_ui(self, transfer_id: str, filename: str, filesize: int):
        box = BoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=48,
            spacing=2,
        )
        lbl = Label(
            text=f"Receiving: {filename}",
            font_size=FS_SM,
            color=T_SECONDARY,
            size_hint_y=None,
            height=22,
            halign="left",
        )
        lbl.bind(size=lambda w, s: setattr(w, "text_size", (s[0], None)))
        pb = ProgressBar(max=100, value=0, size_hint_y=None, height=10)
        # Green fill on incoming progress bars
        with pb.canvas.before:
            Color(*C_GREEN)
            _rect = RoundedRectangle(pos=pb.pos, size=(0, pb.height), radius=[4])

        def _upd_inc_pb(*_):
            ratio = pb.value / pb.max if pb.max > 0 else 0
            _rect.pos = pb.pos
            _rect.size = (pb.width * ratio, pb.height)

        pb.bind(pos=_upd_inc_pb, size=_upd_inc_pb, value=_upd_inc_pb)

        box.add_widget(lbl)
        box.add_widget(pb)
        self.incoming_progress_box.add_widget(box)
        self._active_transfers[transfer_id] = {
            "filename": filename,
            "filesize": filesize,
            "bytes_received": 0,
            "progress_bar": pb,
            "box": box,
            "label": lbl,
        }

    def on_file_progress(self, transfer_id: str, bytes_received: int):
        """Update progress for an active incoming transfer."""
        Clock.schedule_once(lambda dt: self._on_file_progress_ui(transfer_id, bytes_received))

    def _on_file_progress_ui(self, transfer_id: str, bytes_received: int):
        info = self._active_transfers.get(transfer_id)
        if not info:
            return
        info["bytes_received"] = bytes_received
        filesize = info["filesize"]
        if filesize > 0:
            pct = min(100, int(bytes_received / filesize * 100))
            info["progress_bar"].value = pct
            info["label"].text = f"Receiving: {info['filename']} ({pct}%)"

    def on_file_complete(self, transfer_id: str, save_path: str):
        """Called when a file is fully received."""
        Clock.schedule_once(lambda dt: self._on_file_complete_ui(transfer_id, save_path))

    def _on_file_complete_ui(self, transfer_id: str, save_path: str):
        info = self._active_transfers.pop(transfer_id, None)
        if info:
            self.incoming_progress_box.remove_widget(info["box"])
            row = FileRow(
                filename=info["filename"],
                filesize=info["filesize"],
                direction="received",
                path=save_path,
            )
            self.file_list.add_widget(row, index=0)
            self._file_count += 1
            self._update_empty_state()

    def _update_empty_state(self):
        has_files = self._file_count > 0
        self._empty_state.opacity = 0 if has_files else 1
        self._empty_state.disabled = has_files
        self._file_scroll.opacity = 1 if has_files else 0
        self._file_scroll.disabled = not has_files
