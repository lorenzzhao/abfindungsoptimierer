# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Light / dark theme for Qt, the explanation HTML and the charts."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from .. import charts

HTML_LIGHT = {"text": "#222222", "muted": "#6b6b6b", "accent": "#0b5cad", "warn_bg": "#fde7c8", "warn_fg": "#9a4b00",
              "border": "#cccccc", "code_bg": "#f3f3f3", "focus_bg": "#ffe2c2", "focus_fg": "#222222"}
HTML_DARK = {"text": "#e6e6e6", "muted": "#9aa0a6", "accent": "#6cb6ff", "warn_bg": "#5a3b10", "warn_fg": "#f0b060",
             "border": "#444a50", "code_bg": "#2a2f35", "focus_bg": "#7a4a1a", "focus_fg": "#ffffff"}

HERKUNFT_STYLE = {
    "annahme": ("Annahme", "#f6c26b", "#4a2a00"),
    "planung": ("Planung", "#9cc7f2", "#0b2a4a"),
    "angabe": ("Angabe", "#a6dcb0", "#0d3a16"),
    "abgeleitet": ("abgeleitet", "#d6d6d6", "#333333"),
    "berechnet": ("berechnet", "#d6d6d6", "#333333"),
    "illustrativ": ("illustrativ", "#e0c8f0", "#3a1a4a"),
}


class Theme:
    def __init__(self, dark: bool):
        self.dark = dark
        self.html = HTML_DARK if dark else HTML_LIGHT
        self.chart = charts.DARK if dark else charts.LIGHT


def apply(app: QApplication, dark: bool) -> Theme:
    app.setStyle("Fusion")
    p = QPalette()
    if dark:
        base, alt, text, win, btn, hl = "#1f2328", "#262b31", "#e6e6e6", "#24292e", "#2d333b", "#2f6fb0"
    else:
        base, alt, text, win, btn, hl = "#ffffff", "#f5f6f7", "#1f1f1f", "#eef0f2", "#f4f5f6", "#2f6fb0"
    p.setColor(QPalette.ColorRole.Window, QColor(win))
    p.setColor(QPalette.ColorRole.WindowText, QColor(text))
    p.setColor(QPalette.ColorRole.Base, QColor(base))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(alt))
    p.setColor(QPalette.ColorRole.Text, QColor(text))
    p.setColor(QPalette.ColorRole.Button, QColor(btn))
    p.setColor(QPalette.ColorRole.ButtonText, QColor(text))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(base))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor(text))
    p.setColor(QPalette.ColorRole.Highlight, QColor(hl))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    p.setColor(QPalette.ColorRole.Link, QColor("#6cb6ff" if dark else "#0b5cad"))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor("#888888"))
    # clearly greyed-out look for disabled input areas
    off_text, off_base = ("#6b7178", "#262a2f") if dark else ("#a8a8a8", "#f0f0f0")
    dis = QPalette.ColorGroup.Disabled
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText):
        p.setColor(dis, role, QColor(off_text))
    p.setColor(dis, QPalette.ColorRole.Base, QColor(off_base))
    p.setColor(dis, QPalette.ColorRole.Highlight, QColor(off_text))
    app.setPalette(p)
    return Theme(dark)


def system_prefers_dark(app: QApplication) -> bool:
    try:
        from PySide6.QtCore import Qt
        return app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except Exception:  # pragma: no cover - older Qt
        return False
