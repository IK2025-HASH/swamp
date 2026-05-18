"""
widgets.py — Reusable UI components for the Swamp app.
"""

from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.graphics import Color, RoundedRectangle, Ellipse

from src.ui.theme import (
    BG_RAISED, BG_SURFACE,
    C_GREEN,
    T_PRIMARY, T_SECONDARY, T_DIM,
    FS_XS, FS_SM, FS_MD, FS_LG, FS_XXL,
    RADIUS_MD,
    H_HEADER, H_BTN,
)


# ---------------------------------------------------------------------------
# SwampHeader
# ---------------------------------------------------------------------------

class SwampHeader(BoxLayout):
    """
    Standard screen header: optional back button, centred title, optional
    right widget.

    Usage::

        self.header = SwampHeader(title="Devices", back_screen="home")
        # later in on_enter:
        self.header.set_manager(self.manager)
    """

    def __init__(self, title: str, back_screen: str = None,
                 right_widget=None, **kwargs):
        super().__init__(
            orientation="horizontal",
            size_hint_y=None,
            height=H_HEADER,
            spacing=0,
            **kwargs,
        )
        self._back_screen = back_screen
        self._manager = None

        # Background
        with self.canvas.before:
            Color(*BG_RAISED)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[0])
        self.bind(pos=self._upd_bg, size=self._upd_bg)

        # Left: back button or spacer
        if back_screen is not None:
            self._back_btn = Button(
                text="←",
                size_hint=(None, 1),
                width=48,
                font_size="20sp",
                color=T_PRIMARY,
                background_normal="",
                background_color=BG_SURFACE,
            )
            self._back_btn.bind(on_press=self._go_back)
            self.add_widget(self._back_btn)
        else:
            self.add_widget(BoxLayout(size_hint=(None, 1), width=48))

        # Centre: title label
        self._title_lbl = Label(
            text=f"[b]{title}[/b]",
            markup=True,
            font_size=FS_LG,
            color=T_PRIMARY,
            halign="center",
            valign="middle",
        )
        self._title_lbl.bind(size=lambda w, s: setattr(w, "text_size", s))
        self.add_widget(self._title_lbl)

        # Right: provided widget or spacer
        if right_widget is not None:
            right_widget.size_hint = (None, 1)
            if not hasattr(right_widget, "width") or right_widget.width == 100:
                right_widget.width = 48
            self.add_widget(right_widget)
        else:
            self.add_widget(BoxLayout(size_hint=(None, 1), width=48))

    # ------------------------------------------------------------------

    def _upd_bg(self, *_):
        self._bg.pos = self.pos
        self._bg.size = self.size

    def _go_back(self, *_):
        if self._manager and self._back_screen:
            self._manager.current = self._back_screen

    def set_manager(self, manager):
        self._manager = manager

    @property
    def title(self):
        return self._title_lbl.text

    @title.setter
    def title(self, value: str):
        self._title_lbl.text = f"[b]{value}[/b]"


# ---------------------------------------------------------------------------
# StatusDot
# ---------------------------------------------------------------------------

class StatusDot(BoxLayout):
    """
    A small coloured circle + text label row.

    Usage::

        dot = StatusDot(text="Idle", color=T_DIM)
        dot.set_status("Connected", C_SUCCESS)
    """

    def __init__(self, text: str = "Idle", color=T_DIM, **kwargs):
        super().__init__(
            orientation="horizontal",
            size_hint_y=None,
            height=28,
            spacing=6,
            **kwargs,
        )
        self._dot_color = color

        # Dot drawn on a small fixed widget
        self._dot_widget = BoxLayout(size_hint=(None, None), width=12, height=12)
        self._dot_widget.bind(pos=self._redraw_dot, size=self._redraw_dot)
        self.add_widget(self._dot_widget)

        self._label = Label(
            text=text,
            font_size=FS_SM,
            color=T_SECONDARY,
            halign="left",
            valign="middle",
        )
        self._label.bind(size=lambda w, s: setattr(w, "text_size", s))
        self.add_widget(self._label)

        self._redraw_dot()

    def _redraw_dot(self, *_):
        self._dot_widget.canvas.clear()
        with self._dot_widget.canvas:
            Color(*self._dot_color)
            x, y = self._dot_widget.pos
            w, h = self._dot_widget.size
            Ellipse(pos=(x, y), size=(w, h))

    def set_status(self, text: str, color):
        self._dot_color = color
        self._label.text = text
        self._redraw_dot()


# ---------------------------------------------------------------------------
# EmptyState
# ---------------------------------------------------------------------------

class EmptyState(BoxLayout):
    """
    Vertically-centred placeholder shown when a list is empty.

    Usage::

        self._empty = EmptyState(
            icon="⊙",
            title="No devices found",
            subtitle="Start the server and join the same WiFi",
        )
        # show/hide via opacity + disabled
    """

    def __init__(self, icon: str = "○", title: str = "Nothing here yet",
                 subtitle: str = "", **kwargs):
        super().__init__(
            orientation="vertical",
            spacing=8,
            **kwargs,
        )

        # Top spacer
        self.add_widget(Label())

        self._icon_lbl = Label(
            text=icon,
            font_size=FS_XXL,
            color=T_DIM,
            size_hint_y=None,
            height=48,
            halign="center",
        )
        self._icon_lbl.bind(size=lambda w, s: setattr(w, "text_size", (s[0], None)))
        self.add_widget(self._icon_lbl)

        self._title_lbl = Label(
            text=title,
            font_size=FS_LG,
            color=T_SECONDARY,
            size_hint_y=None,
            height=32,
            halign="center",
        )
        self._title_lbl.bind(size=lambda w, s: setattr(w, "text_size", (s[0], None)))
        self.add_widget(self._title_lbl)

        if subtitle:
            self._subtitle_lbl = Label(
                text=subtitle,
                font_size=FS_SM,
                color=T_DIM,
                size_hint_y=None,
                height=24,
                halign="center",
            )
            self._subtitle_lbl.bind(size=lambda w, s: setattr(w, "text_size", (s[0], None)))
            self.add_widget(self._subtitle_lbl)

        # Bottom spacer
        self.add_widget(Label())


# ---------------------------------------------------------------------------
# SwampButton
# ---------------------------------------------------------------------------

class SwampButton(Button):
    """
    A rounded Kivy button that draws its own RoundedRectangle background,
    making the default Kivy button background invisible.

    Usage::

        btn = SwampButton("Be Master  ★", color=C_MASTER)
        btn.bind(on_press=handler)
    """

    def __init__(self, text: str, color=C_GREEN, text_color=T_PRIMARY,
                 height: int = H_BTN, **kwargs):
        # Remove height from kwargs if passed as positional-style kw to avoid conflict
        kwargs.pop("height", None)
        super().__init__(
            text=text,
            size_hint_y=None,
            height=height,
            font_size=FS_MD,
            color=text_color,
            background_normal="",
            background_color=(0, 0, 0, 0),   # transparent — we draw our own
            **kwargs,
        )
        self._btn_color = color

        with self.canvas.before:
            self._color_instr = Color(*color)
            self._rect = RoundedRectangle(pos=self.pos, size=self.size, radius=RADIUS_MD)

        self.bind(pos=self._upd_rect, size=self._upd_rect)

    def _upd_rect(self, *_):
        self._rect.pos = self.pos
        self._rect.size = self.size

    @property
    def btn_color(self):
        return self._btn_color

    @btn_color.setter
    def btn_color(self, value):
        self._btn_color = value
        self._color_instr.rgba = value
