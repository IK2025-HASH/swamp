"""
main_minimal.py — Swamp minimal proof-of-concept APK entry point.

Single screen, two role buttons, a status label.
No network, no camera, no native libs — just Kivy.
Purpose: prove the build pipeline produces a working APK.
"""

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.widget import Widget
from kivy.graphics import Color, RoundedRectangle
from kivy.utils import platform


class SwampMinimalApp(App):
    title = "Swamp"

    def build(self):
        root = BoxLayout(
            orientation="vertical",
            padding=[32, 48, 32, 48],
            spacing=24,
        )
        root.canvas.before.clear()
        with root.canvas.before:
            Color(0.08, 0.10, 0.12, 1)   # dark background
            self._bg = RoundedRectangle(pos=root.pos, size=root.size)
        root.bind(pos=self._update_bg, size=self._update_bg)

        # Title
        title = Label(
            text="SWAMP",
            font_size="32sp",
            bold=True,
            color=(1, 1, 1, 1),
            size_hint=(1, None),
            height=56,
        )
        root.add_widget(title)

        subtitle = Label(
            text="Peer-to-peer mobile exchange",
            font_size="14sp",
            color=(0.5, 0.6, 0.7, 1),
            size_hint=(1, None),
            height=28,
        )
        root.add_widget(subtitle)

        root.add_widget(Widget(size_hint=(1, 0.1)))

        # Master button
        self.master_btn = self._make_button(
            "★  Be the Master",
            (0.95, 0.60, 0.10, 1),
            self._on_master,
        )
        root.add_widget(self.master_btn)

        # Node button
        self.node_btn = self._make_button(
            "⊙  Join as Node",
            (0.15, 0.65, 0.85, 1),
            self._on_node,
        )
        root.add_widget(self.node_btn)

        root.add_widget(Widget(size_hint=(1, 0.1)))

        # Status label
        self.status = Label(
            text="Choose a role to start",
            font_size="13sp",
            color=(0.5, 0.6, 0.7, 1),
            size_hint=(1, None),
            height=40,
        )
        root.add_widget(self.status)

        # Platform info
        plat = Label(
            text=f"Running on: {platform}  ·  Build pipeline ✓",
            font_size="11sp",
            color=(0.3, 0.4, 0.45, 1),
            size_hint=(1, None),
            height=28,
        )
        root.add_widget(plat)

        return root

    def _make_button(self, text, color, callback):
        btn = Button(
            text=text,
            font_size="17sp",
            size_hint=(1, None),
            height=56,
            background_color=(0, 0, 0, 0),
            color=(1, 1, 1, 1),
        )
        with btn.canvas.before:
            Color(*color)
            btn._rect = RoundedRectangle(
                pos=btn.pos, size=btn.size, radius=[12]
            )
        btn.bind(
            pos=lambda w, v: setattr(w._rect, "pos", v),
            size=lambda w, v: setattr(w._rect, "size", v),
            on_press=callback,
        )
        return btn

    def _on_master(self, *_):
        self.status.text = "★  Running as Master — waiting for nodes…"
        self.status.color = (0.95, 0.60, 0.10, 1)

    def _on_node(self, *_):
        self.status.text = "⊙  Running as Node — looking for master…"
        self.status.color = (0.15, 0.65, 0.85, 1)

    def _update_bg(self, instance, value):
        self._bg.pos = instance.pos
        self._bg.size = instance.size


if __name__ == "__main__":
    SwampMinimalApp().run()
