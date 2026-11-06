# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Chart tabs (embedded matplotlib). Only the visible chart is redrawn; clicking a chart
focuses the matching result."""

from __future__ import annotations

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Signal
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QScrollArea, QTabWidget, QToolTip, QVBoxLayout, QWidget

from ..dates import fmt_eur

from .. import charts
from ..engine.marginal import Knick, curves, knick

TABS = [("kink", "Steuer && Knick"), ("gantt", "Zeitleiste"), ("liq", "Liquidität")]


class ChartPanel(QWidget):
    focusRequested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.canvases = {}
        self.figs = {}
        for key, title in TABS:
            w = QWidget()
            v = QVBoxLayout(w)
            v.setContentsMargins(0, 0, 0, 0)
            fig = Figure(figsize=(7, 4.2), dpi=90)
            cv = FigureCanvasQTAgg(fig)
            cv.mpl_connect("button_press_event", lambda ev, k=key: self._clicked(k, ev))
            if key == "kink":
                cv.mpl_connect("motion_notify_event", self._knick_hover)
            if key in ("kink", "gantt"):  # kink: three stacked parts; gantt: dates and a long legend – scrollable
                cv.setMinimumHeight(820 if key == "kink" else 600)
                sa = QScrollArea()
                sa.setWidgetResizable(True)
                sa.setWidget(cv)
                v.addWidget(sa, 1)
            else:
                v.addWidget(cv, 1)
            self.tabs.addTab(w, title)
            self.canvases[key] = cv
            self.figs[key] = fig
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.tabs)
        self.tabs.currentChanged.connect(lambda _: self.redraw())
        self.res = None
        self.legal = None
        self.focus = None
        self.theme = charts.LIGHT
        self.dirty = {k for k, _ in TABS}

    def set_data(self, res, legal, focus, theme) -> None:
        self.res, self.legal, self.focus, self.theme = res, legal, focus, theme
        self.dirty = {k for k, _ in TABS}
        self.redraw()

    def set_focus(self, focus) -> None:
        self.focus = focus
        self.dirty |= {"kink", "gantt", "liq"}
        self.redraw()

    def redraw(self) -> None:
        if not self.res:
            return
        key = TABS[self.tabs.currentIndex()][0]
        if key not in self.dirty:
            return
        fig, th, r = self.figs[key], self.theme, self.res
        if key == "kink":
            charts.chart_kink(fig, curves(r), th, self.focus, knick(r))
        elif key == "gantt":
            charts.chart_gantt(fig, r, th, self.focus)
        elif key == "liq":
            charts.chart_liquidity(fig, r, th, self.focus)
        self.canvases[key].draw_idle()
        self.dirty.discard(key)

    def _knick_hover(self, ev) -> None:
        """Tooltip with x, y and zone on the Ä8 chart."""
        fig = self.figs["kink"]
        kn = getattr(fig, "_knick", None)
        if kn is None or ev.inaxes is not getattr(fig, "_knick_ax", None) or ev.xdata is None:
            QToolTip.hideText()
            return
        i = min(range(len(kn.x)), key=lambda k: abs(kn.x[k] - ev.xdata))
        x = kn.x[i]
        lines = "<br/>".join(f"{lab}: <b>{ys[i]:.0f} %</b>" for lab, ys in kn.lines.items())
        QToolTip.showText(QCursor.pos(), f"<qt>übriges zvE <b>{fmt_eur(x)}</b><br/>{lines}<br/>"
                                          f"<i>Zone: {Knick.zone(x, kn.alg)}</i></qt>", self.canvases["kink"])

    def _clicked(self, key: str, ev) -> None:
        if not self.res or ev.xdata is None:
            return
        u = self.res.main_unit_year()
        if key == "kink" and u:
            self.focusRequested.emit(f"est_{u.key}{u.year}" if ev.inaxes is self.figs[key].axes[0] else f"nullgrenze_{u.key}{u.year}")
        elif key == "gantt":
            persons = self.res.settings.persons
            row = len(persons) - 1 - int(round(ev.ydata / charts.ROW_GAP))
            if 0 <= row < len(persons):
                self.focusRequested.emit(f"alg_{persons[row].id}_total")
        elif key == "liq":
            self.focusRequested.emit("liq_min")

