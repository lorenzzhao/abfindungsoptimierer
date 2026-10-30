# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Area 2: calculated results. Each value can be focused by clicking; only one at a time."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import QHeaderView, QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from ..dates import fmt_eur
from ..explain import group_rank

ROLE_ID = Qt.ItemDataRole.UserRole


class ResultsPanel(QWidget):
    focusChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.focus_id: str | None = None
        self.items: dict[str, QTreeWidgetItem] = {}
        self.collapsed: set[str] = set()
        self.colors = {"focus_bg": "#ffe2c2", "focus_fg": "#222222", "warn_fg": "#9a4b00"}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.header = QLabel()
        self.header.setTextFormat(Qt.TextFormat.RichText)
        self.header.setWordWrap(True)
        lay.addWidget(self.header)
        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Ergebnis (Klick = fokussieren)", "Wert"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.setAlternatingRowColors(True)
        self.tree.itemClicked.connect(self._clicked)
        self.tree.itemCollapsed.connect(lambda it: self.collapsed.add(it.text(0)))
        self.tree.itemExpanded.connect(lambda it: self.collapsed.discard(it.text(0)))
        self.tree.currentItemChanged.connect(lambda cur, _prev: self._clicked(cur) if cur else None)
        lay.addWidget(self.tree, 1)

    def set_colors(self, html_colors: dict) -> None:
        self.colors = html_colors
        self._highlight()

    def update_results(self, res) -> None:
        rs = res.rs
        self.tree.blockSignals(True)
        self.tree.clear()
        self.items = {}
        groups: dict[str, list] = {}
        for t in rs.values():
            if t.id.startswith("_"):
                continue
            groups.setdefault(t.group or "Übersicht", []).append(t)
        bold = QFont()
        bold.setBold(True)
        for g in sorted(groups, key=group_rank):
            gi = QTreeWidgetItem([g, ""])
            gi.setFont(0, bold)
            gi.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.tree.addTopLevelItem(gi)
            for t in groups[g]:
                mark = ""
                if "warnung" in t.flags:
                    mark = "⚠ "
                elif t.uncertain:
                    mark = "≈ "
                it = QTreeWidgetItem([mark + t.label, t.fmt()])
                it.setData(0, ROLE_ID, t.id)
                it.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                tip = "Unsicher: beruht auf einer Annahme, fortgeschriebenem oder ungeprüftem Parameter." if mark == "≈ " else ""
                it.setToolTip(0, tip)
                gi.addChild(it)
                self.items[t.id] = it
            gi.setExpanded(g not in self.collapsed)
        self.tree.blockSignals(False)
        o = res.settings.options
        self.header.setText(
            f"<span style='font-size:15pt'><b>Saldo {o.horizon_start}–{o.horizon_end}: {fmt_eur(res.saldo)}</b></span>"
            f"<br/><small>Steuer {fmt_eur(sum(res.tax_by_year.values()))} · ALG {fmt_eur(sum(res.alg_by_year.values()))} · "
            f"eigene KV {fmt_eur(sum(res.kv_by_year.values()))} · Gegenwert Gestaltungen {fmt_eur(res.gebunden)} · "
            f"Liquiditätstiefpunkt {fmt_eur(res.liq_min)} · {len(res.warnings)} Hinweis(e)</small>")
        if self.focus_id not in self.items:
            self.focus_id = "saldo" if "saldo" in self.items else next(iter(self.items), None)
        self._highlight()

    def set_focus(self, fid: str) -> None:
        if fid not in self.items:
            return
        if fid != self.focus_id:
            self.focus_id = fid
            self._highlight()
            self.focusChanged.emit(fid)
        it = self.items[fid]
        self.tree.scrollToItem(it)

    def _clicked(self, item: QTreeWidgetItem, *_):
        fid = item.data(0, ROLE_ID)
        if fid:
            self.set_focus(fid)

    def _highlight(self) -> None:
        bg = QBrush(QColor(self.colors.get("focus_bg", "#ffe2c2")))
        fg = QBrush(QColor(self.colors.get("focus_fg", "#222222")))
        for fid, it in self.items.items():
            f = it.font(0)
            on = fid == self.focus_id
            f.setBold(on)
            for col in (0, 1):
                it.setFont(col, f)
                it.setBackground(col, bg if on else QBrush())
                it.setForeground(col, fg if on else QBrush())
            txt = it.text(0)
            if on and not txt.startswith("▶ "):
                it.setText(0, "▶ " + txt)
            elif not on and txt.startswith("▶ "):
                it.setText(0, txt[2:])
