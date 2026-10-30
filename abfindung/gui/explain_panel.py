# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Area 3: dynamic explanation of the focused result."""

from __future__ import annotations

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QLabel, QTextBrowser, QVBoxLayout, QWidget

from .. import explain


class ExplainPanel(QWidget):
    focusRequested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(QLabel("<b>Erklärung</b> <small>(zum fokussierten Ergebnis; Links wechseln den Fokus)</small>"))
        self.view = QTextBrowser()
        self.view.setOpenLinks(False)
        self.view.anchorClicked.connect(self._link)
        lay.addWidget(self.view, 1)
        self.colors = {}

    def show_result(self, res, fid: str | None, colors: dict) -> None:
        self.colors = colors
        if not res or not fid or fid not in res.rs:
            self.view.setHtml("<p>Kein Ergebnis fokussiert.</p>")
            return
        e = explain.build(res.rs[fid], res.tracer.legal, res.rs)
        bar = self.view.verticalScrollBar().value() if getattr(self, "_last", None) == fid else 0
        self.view.setHtml(explain.to_html(e, colors))
        self.view.verticalScrollBar().setValue(bar)
        self._last = fid

    def _link(self, url: QUrl) -> None:
        s = url.toString()
        if s.startswith("focus:"):
            self.focusRequested.emit(s[len("focus:"):])
        else:
            QDesktopServices.openUrl(url)
