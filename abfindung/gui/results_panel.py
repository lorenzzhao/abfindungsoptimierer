# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Area 2: calculated results. Each value can be focused by clicking; only one at a time.

Switches above the list hide areas that do not enter the target value (Netto-Saldo) directly, such as the liquidity.
They only change the display; the calculation and the optimisation always use everything."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import (QCheckBox, QHBoxLayout, QHeaderView, QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                               QWidget)

from ..dates import fmt_eur
from ..explain import group_sort_key

ROLE_ID = Qt.ItemDataRole.UserRole

# (key, label, tooltip, shown by default)
OPTIONAL = [
    ("steuer_details", "Steuer-Zwischenwerte",
     "Zwischenschritte der Steuerberechnung je Jahr (Einkünfte, Vorsorge, zvE, ESt, Soli, KiSt …). Sie sind in der "
     "Steuer des Jahres bereits enthalten; angezeigt bleiben die Steuer und die Veranlagungsart.", False),
    ("liquiditaet", "Liquidität",
     "Lohnsteuerabzug, Erstattungen/Nachzahlungen und Liquiditätstiefpunkt: wann Geld fließt, nicht wie viel am Ende "
     "bleibt. Gehen nicht in den Netto-Saldo ein.", False),
    ("abgeleitet", "Abgeleitete Termine",
     "Aus den Eingaben abgeleitete Termine, z. B. die Arbeitsuchendmeldung. Gehen nicht in den Netto-Saldo ein.", True),
    ("hinweise", "Hinweise", "Hinweise und Warnungen zur Berechnung.", True),
]


def category(t) -> str | None:
    """Key of the optional area a result belongs to, None if it is always shown."""
    g = t.group or ""
    if g == "Liquidität":
        return "liquiditaet"
    if g.startswith("Abgeleitete Werte"):
        return "abgeleitet"
    if g == "Hinweise und Warnungen":
        return "hinweise"
    if g.startswith("Steuer ") and not t.id.startswith(("steuer_", "veranlagung_")):
        return "steuer_details"
    return None


class ResultsPanel(QWidget):
    focusChanged = Signal(str)

    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.qs = settings
        self.res = None
        self.cats: dict[str, str | None] = {}
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
        row = QHBoxLayout()
        row.addWidget(QLabel("Anzeigen:"))
        self.toggles: dict[str, QCheckBox] = {}
        for key, label, tip, default in OPTIONAL:
            cb = QCheckBox(label)
            cb.setToolTip(tip + " Nur Anzeige – Berechnung und Optimierung berücksichtigen immer alles.")
            stored = self.qs.value(f"results/{key}") if self.qs is not None else None
            cb.setChecked(default if stored is None else str(stored).lower() in ("true", "1"))
            cb.toggled.connect(lambda on, k=key: self._toggled(k, on))
            row.addWidget(cb)
            self.toggles[key] = cb
        row.addStretch(1)
        lay.addLayout(row)
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

    def shown(self, key: str | None) -> bool:
        return key is None or self.toggles[key].isChecked()

    def _toggled(self, key: str, on: bool) -> None:
        if self.qs is not None:
            self.qs.setValue(f"results/{key}", on)
        if self.res is None:
            return
        self._apply_visibility()
        self._set_header()
        if self.focus_id and not self.shown(self.cats.get(self.focus_id)):
            self.set_focus("saldo")

    def _apply_visibility(self) -> None:
        for i in range(self.tree.topLevelItemCount()):
            gi = self.tree.topLevelItem(i)
            visible = 0
            for j in range(gi.childCount()):
                it = gi.child(j)
                hide = not self.shown(self.cats.get(it.data(0, ROLE_ID)))
                it.setHidden(hide)
                visible += not hide
            gi.setHidden(visible == 0)

    def _set_header(self) -> None:
        res = self.res
        o = res.settings.options
        parts = [f"Steuer {fmt_eur(sum(res.tax_by_year.values()))}"]
        if any(ps.austritt and ps.alg_aktiv for ps in res.settings.persons):
            parts.append(f"ALG {fmt_eur(sum(res.alg_by_year.values()))}")
        parts.append(f"eigene KV {fmt_eur(sum(res.kv_by_year.values()))}")
        if res.gebunden:
            parts.append(f"Gegenwert Gestaltungen {fmt_eur(res.gebunden)}")
        if self.shown("liquiditaet"):
            parts.append(f"Liquiditätstiefpunkt {fmt_eur(res.liq_min)}")
        if res.warnings:
            parts.append(f"{len(res.warnings)} Hinweis(e)")
        self.header.setText(
            f"<span style='font-size:15pt'><b>Saldo {o.horizon_start}–{o.horizon_end}: {fmt_eur(res.saldo)}</b></span>"
            f"<br/><small>{' · '.join(parts)}</small>")

    def update_results(self, res) -> None:
        self.res = res
        rs = res.rs
        self.cats = {t.id: category(t) for t in rs.values()}
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
        for g in sorted(groups, key=group_sort_key(res.settings)):
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
        self._apply_visibility()
        self.tree.blockSignals(False)
        self._set_header()
        if self.focus_id not in self.items or not self.shown(self.cats.get(self.focus_id)):
            self.focus_id = "saldo" if "saldo" in self.items else next(iter(self.items), None)
        self._highlight()

    def set_focus(self, fid: str) -> None:
        if fid not in self.items:
            return
        key = self.cats.get(fid)
        if not self.shown(key):  # e.g. a link in the explanation to a hidden value: show its area
            self.toggles[key].setChecked(True)
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
