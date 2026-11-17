# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Input controls bound to a settings path: slider + spin box, date slider, month slider, …

Each control shows its label, an origin badge (herkunft; Annahme highlighted)
and a tooltip with the legal references.
"""

from __future__ import annotations

import time
from datetime import date, timedelta

from PySide6.QtCore import QDate, QEvent, QObject, Qt, Signal
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (QAbstractScrollArea, QAbstractSlider, QAbstractSpinBox, QApplication, QCheckBox, QComboBox, QDateEdit,
                             QDoubleSpinBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSlider, QSpinBox, QToolButton,
                             QWidget)

from ..dates import MONTHS_DE
from .theme import HERKUNFT_STYLE


class WheelGuard(QObject):
    """Mouse wheel over an input only changes its value with Ctrl held down.

    Without Ctrl the wheel is passed to the scroll bar of the enclosing scroll area, so scrolling
    through the panel never changes a value by accident. With Ctrl it is re-sent without the
    modifier, so it moves by one normal step (Qt would otherwise use 10x / page steps).
    It also records whether a mouse button is held on a spin box, so the main window can postpone the
    recalculation until the arrow button is released (otherwise auto-repeat adds a second step).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._forwarding = False
        self._held = False  # a mouse button was pressed on a spin box and not yet released
        self._held_since = 0.0

    @property
    def spin_held(self) -> bool:
        """A mouse button is held on a spin box (see MainWindow._recalc_when_released). A missed release event
        (touch pad tap, focus or window change, a rebuilt panel) must never block the calculation for good: the
        flag only counts while the system still reports a pressed button, and for at most two seconds."""
        if self._held and (not QApplication.mouseButtons() or time.monotonic() - self._held_since > 2.0):
            self._held = False
        return self._held

    def eventFilter(self, obj, ev) -> bool:
        t = ev.type()
        if isinstance(obj, QAbstractSpinBox):
            if t == QEvent.Type.MouseButtonPress:
                self._held, self._held_since = True, time.monotonic()
            elif t == QEvent.Type.MouseButtonRelease:
                self._held = False
        if t != QEvent.Type.Wheel or self._forwarding:
            return False
        ctrl = bool(ev.modifiers() & Qt.KeyboardModifier.ControlModifier)
        plain = QWheelEvent(ev.position(), ev.globalPosition(), ev.pixelDelta(), ev.angleDelta(), ev.buttons(),
                            ev.modifiers() & ~Qt.KeyboardModifier.ControlModifier, ev.phase(), ev.inverted())
        target = obj if ctrl else self._scrollbar(obj)
        if target is not None:
            self._forwarding = True
            try:
                QApplication.sendEvent(target, plain)
            finally:
                self._forwarding = False
        ev.accept()
        return True

    @staticmethod
    def _scrollbar(w: QWidget):
        """Vertical scroll bar of the enclosing scroll area (receives the wheel instead of the input)."""
        p = w.parentWidget()
        while p is not None and not isinstance(p, QAbstractScrollArea):
            p = p.parentWidget()
        return p.verticalScrollBar() if p is not None else None

    def install(self, root: QWidget) -> None:
        for w in root.findChildren(QWidget):
            if isinstance(w, (QAbstractSpinBox, QAbstractSlider, QComboBox)) and not w.property("_wheel_guard"):
                w.installEventFilter(self)
                w.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # the wheel alone does not focus the input
                w.setProperty("_wheel_guard", True)


def compact_combo(c: QComboBox) -> QComboBox:
    """Keep long item texts from widening the input panel."""
    c.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    c.setMinimumContentsLength(12)
    return c


CHANGED_COLOR = "#d32f2f"  # red marker for values / origins changed since the last load or save


class Bound(QWidget):
    changed = Signal(str, object)
    originClicked = Signal(str, object)  # path, global position of the click
    resetRequested = Signal(str, str)    # path, what: "value" | "origin" | "both" (Ctrl + left click)

    def __init__(self, path: str, label: str, tooltip: str = "", parent=None):
        super().__init__(parent)
        self.path = path
        self._lay = QGridLayout(self)
        self._lay.setContentsMargins(0, 2, 0, 2)
        self._lay.setHorizontalSpacing(6)
        self._lay.setVerticalSpacing(1)
        self.lbl = QLabel(label)
        self.lbl.setWordWrap(True)
        self.badge = QLabel()
        self.badge.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.badge.setCursor(Qt.CursorShape.PointingHandCursor)
        self.badge.mousePressEvent = self._badge_click
        # change marker: own widget with its own tooltip (does not interfere with the label tooltip)
        self.dot = QLabel()
        self.dot.setFixedWidth(10)
        self.dot.setStyleSheet(f"color:{CHANGED_COLOR}; font-size:9pt;")
        self.dot.mousePressEvent = lambda ev: self._ctrl_reset(ev, "value", self.dot)
        self.lbl.mousePressEvent = self._label_click
        # marker for a changed origin, directly in front of the badge
        self.odot = QLabel()
        self.odot.setStyleSheet(f"color:{CHANGED_COLOR}; font-size:9pt;")
        self.odot.mousePressEvent = lambda ev: self._ctrl_reset(ev, "origin", self.odot)
        self.badge_box = QWidget()
        bl = QHBoxLayout(self.badge_box)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(2)
        bl.addWidget(self.odot)
        bl.addWidget(self.badge)
        self._lay.addWidget(self.dot, 0, 0)
        self._lay.addWidget(self.lbl, 0, 1)
        self._lay.addWidget(self.badge_box, 0, 2, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        self._lay.setColumnStretch(1, 1)
        self._herkunft = ""
        if tooltip:
            self.setToolTip(tooltip)

    def add_editor(self, w: QWidget) -> None:
        self._lay.addWidget(w, 1, 1, 1, 2)

    def _badge_click(self, ev) -> None:
        """Click: choose the origin. Ctrl + click: reset a changed origin to the saved one."""
        if ev.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if self.odot.text():
                self.resetRequested.emit(self.path, "origin")
            return
        self.originClicked.emit(self.path, ev.globalPosition().toPoint())

    def _ctrl_reset(self, ev, what: str, marker: QLabel) -> None:
        if ev.modifiers() & Qt.KeyboardModifier.ControlModifier and marker.text():
            self.resetRequested.emit(self.path, what)

    def _label_click(self, ev) -> None:
        if ev.modifiers() & Qt.KeyboardModifier.ControlModifier and (self.dot.text() or self.odot.text()):
            self.resetRequested.emit(self.path, "both")

    def set_changed(self, value_tip: str = "", origin_tip: str = "") -> None:
        """Red marker in front of the label (value changed) and in front of the badge (origin changed),
        each with its own tooltip showing the saved state."""
        hint = "<br/><i>Strg + Klick: auf den gespeicherten Stand zurücksetzen</i>"
        self.dot.setText("●" if value_tip else "")
        self.dot.setToolTip(value_tip + hint if value_tip else "")
        self.odot.setText("●" if origin_tip else "")
        self.odot.setToolTip(origin_tip + hint if origin_tip else "")

    def set_origin(self, herkunft: str) -> None:
        self._herkunft = herkunft
        label, bg, fg = HERKUNFT_STYLE.get(herkunft, (herkunft, "#d6d6d6", "#333333"))
        self.badge.setText(f" {label} ")
        self.badge.setStyleSheet(f"QLabel {{background:{bg}; color:{fg}; border-radius:3px; font-size:8pt;}}"
                                 "QLabel:disabled {background:#d0d0d0; color:#8a8a8a;}")
        self.badge.setToolTip("Herkunft des Werts" + (" – unsicher, bitte prüfen" if herkunft == "annahme" else "")
                              + ". Klicken: Herkunft festlegen; Strg + Klick: geänderte Herkunft zurücksetzen.")

    def set_value(self, v) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    def editors(self) -> list:
        """The input widgets (locked while the program derives the value)."""
        return []

    def set_derived(self, on: bool, tip: str = "") -> None:
        """Origin "abgeleitet" for a value the program determines itself: inputs locked, explanation as tooltip."""
        if not hasattr(self, "_plain_tip"):
            self._plain_tip = self.toolTip()
        for w in self.editors():
            if w is not None:
                w.setEnabled(not on)
                w.setToolTip(tip if on else "")
        self.setToolTip((tip + ("<hr/>" + self._plain_tip if self._plain_tip else "")) if on else self._plain_tip)

    def _emit(self, v) -> None:
        self.changed.emit(self.path, v)


class NumberEdit(Bound):
    """Slider + spin box for amounts, shares (factor 100 for %) or plain numbers."""

    def __init__(self, path, label, lo, hi, step, decimals=0, suffix=" €", factor=1.0, slider=True, tooltip="",
                 integer=False):
        super().__init__(path, label, tooltip)
        self.lo, self.hi, self.step, self.factor, self.integer = lo, hi, step, factor, integer
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        self.slider = QSlider(Qt.Orientation.Horizontal) if slider else None
        self.spin = QDoubleSpinBox()
        self.spin.setDecimals(decimals)
        self.spin.setSuffix(suffix)
        self.spin.setSingleStep(step * factor)
        self.spin.setGroupSeparatorShown(True)
        self.spin.setKeyboardTracking(False)
        self.spin.setMinimumWidth(105)
        self.spin.setMaximumWidth(140)
        self._set_ranges(lo, hi)
        if self.slider:
            h.addWidget(self.slider, 1)
            self.slider.valueChanged.connect(self._slider_moved)
        h.addWidget(self.spin, 0 if slider else 1)
        self.spin.valueChanged.connect(self._spin_changed)
        self.add_editor(row)

    def _set_ranges(self, lo, hi):
        self.lo, self.hi = lo, hi
        self.spin.setRange(lo * self.factor, hi * self.factor)
        if self.slider:
            self.slider.setRange(0, max(1, int(round((hi - lo) / self.step))))

    def editors(self) -> list:
        return [self.slider, self.spin]

    def set_value(self, v) -> None:
        v = float(v or 0)
        if v < self.lo or v > self.hi:
            self._set_ranges(min(self.lo, v), max(self.hi, v))
        for w in (self.slider, self.spin):
            if w:
                w.blockSignals(True)
        self.spin.setValue(v * self.factor)
        if self.slider:
            self.slider.setValue(int(round((v - self.lo) / self.step)))
        for w in (self.slider, self.spin):
            if w:
                w.blockSignals(False)

    def _out(self, v: float):
        return int(round(v)) if self.integer else v

    def _slider_moved(self, i: int) -> None:
        v = self.lo + i * self.step
        self.spin.blockSignals(True)
        self.spin.setValue(v * self.factor)
        self.spin.blockSignals(False)
        self._emit(self._out(v))

    def _spin_changed(self, x: float) -> None:
        v = x / self.factor
        if self.slider:
            self.slider.blockSignals(True)
            self.slider.setValue(int(round((v - self.lo) / self.step)))
            self.slider.blockSignals(False)
        self._emit(self._out(v))


class IntEdit(Bound):
    def __init__(self, path, label, lo, hi, suffix="", tooltip=""):
        super().__init__(path, label, tooltip)
        self.spin = QSpinBox()
        self.spin.setRange(lo, hi)
        self.spin.setSuffix(suffix)
        self.spin.setKeyboardTracking(False)
        self.spin.valueChanged.connect(lambda v: self._emit(int(v)))
        self.add_editor(self.spin)

    def editors(self) -> list:
        return [self.spin]

    def set_value(self, v) -> None:
        self.spin.blockSignals(True)
        if v < self.spin.minimum() or v > self.spin.maximum():
            self.spin.setRange(min(self.spin.minimum(), v), max(self.spin.maximum(), v))
        self.spin.setValue(int(v))
        self.spin.blockSignals(False)


def _qd(d: date) -> QDate:
    return QDate(d.year, d.month, d.day)


def _pd(q: QDate) -> date:
    return date(q.year(), q.month(), q.day())


class DateEdit(Bound):
    """Date slider (day steps) + calendar date edit."""

    def __init__(self, path, label, lo: date, hi: date, slider=True, tooltip=""):
        super().__init__(path, label, tooltip)
        self.lo, self.hi = lo, hi
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        self.slider = QSlider(Qt.Orientation.Horizontal) if slider else None
        self.edit = QDateEdit()
        self.edit.setCalendarPopup(True)
        self.edit.setDisplayFormat("dd.MM.yyyy")
        self.edit.setDateRange(_qd(lo), _qd(hi))
        self.edit.setKeyboardTracking(False)
        if self.slider:
            self.slider.setRange(0, (hi - lo).days)
            self.slider.valueChanged.connect(self._slider_moved)
            h.addWidget(self.slider, 1)
        h.addWidget(self.edit)
        self.edit.dateChanged.connect(self._edit_changed)
        self.add_editor(row)

    def editors(self) -> list:
        return [self.slider, self.edit]

    def set_value(self, v: date) -> None:
        if v < self.lo or v > self.hi:
            self.lo, self.hi = min(self.lo, v), max(self.hi, v)
            self.edit.setDateRange(_qd(self.lo), _qd(self.hi))
            if self.slider:
                self.slider.setRange(0, (self.hi - self.lo).days)
        for w in (self.slider, self.edit):
            if w:
                w.blockSignals(True)
        self.edit.setDate(_qd(v))
        if self.slider:
            self.slider.setValue((v - self.lo).days)
        for w in (self.slider, self.edit):
            if w:
                w.blockSignals(False)

    def _slider_moved(self, i: int) -> None:
        d = self.lo + timedelta(days=i)
        self.edit.blockSignals(True)
        self.edit.setDate(_qd(d))
        self.edit.blockSignals(False)
        self._emit(d)

    def _edit_changed(self, q: QDate) -> None:
        d = _pd(q)
        if self.slider:
            self.slider.blockSignals(True)
            self.slider.setValue((d - self.lo).days)
            self.slider.blockSignals(False)
        self._emit(d)


class MonthEdit(Bound):
    """Slider over month indices (year*12 + month-1)."""

    def __init__(self, path, label, lo_idx: int, hi_idx: int, tooltip=""):
        super().__init__(path, label, tooltip)
        self.lo, self.hi = lo_idx, hi_idx
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, hi_idx - lo_idx)
        self.slider.setPageStep(12)
        self.slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.slider.setTickInterval(12)
        self.text = QLabel()
        self.text.setMinimumWidth(70)
        h.addWidget(self.slider, 1)
        h.addWidget(self.text)
        self.slider.valueChanged.connect(self._moved)
        self.add_editor(row)

    def _fmt(self, idx: int) -> str:
        return f"{MONTHS_DE[idx % 12]} {idx // 12}"

    def editors(self) -> list:
        return [self.slider]

    def set_value(self, v: int) -> None:
        if v < self.lo or v > self.hi:
            self.lo, self.hi = min(self.lo, v), max(self.hi, v)
            self.slider.setRange(0, self.hi - self.lo)
        self.slider.blockSignals(True)
        self.slider.setValue(v - self.lo)
        self.slider.blockSignals(False)
        self.text.setText(self._fmt(v))

    def _moved(self, i: int) -> None:
        v = self.lo + i
        self.text.setText(self._fmt(v))
        self._emit(v)


class ChoiceEdit(Bound):
    def __init__(self, path, label, options: list[tuple[object, str]], tooltip=""):
        super().__init__(path, label, tooltip)
        self.options = options
        self.combo = QComboBox()
        compact_combo(self.combo)
        for _, text in options:
            self.combo.addItem(text)
        self.combo.currentIndexChanged.connect(lambda i: self._emit(self.options[i][0]) if i >= 0 else None)
        self.add_editor(self.combo)

    def editors(self) -> list:
        return [self.combo]

    def set_value(self, v) -> None:
        self.combo.blockSignals(True)
        for i, (val, _) in enumerate(self.options):
            if val == v:
                self.combo.setCurrentIndex(i)
                break
        self.combo.blockSignals(False)


class BoolEdit(Bound):
    """Check box; the text is a separate word-wrapping label (clicking it toggles)."""

    def __init__(self, path, label, tooltip=""):
        super().__init__(path, label, tooltip)
        self.check = QCheckBox()
        self.check.toggled.connect(lambda b: self._emit(bool(b)))
        self._lay.removeWidget(self.dot)
        self._lay.removeWidget(self.lbl)
        self._lay.removeWidget(self.badge_box)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.dot, 0, Qt.AlignmentFlag.AlignTop)
        row.addWidget(self.check, 0, Qt.AlignmentFlag.AlignTop)
        row.addWidget(self.lbl, 1)
        row.addWidget(self.badge_box, 0, Qt.AlignmentFlag.AlignTop)
        self._lay.addLayout(row, 0, 0, 1, 3)

    def _label_click(self, ev) -> None:
        if ev.modifiers() & Qt.KeyboardModifier.ControlModifier:
            super()._label_click(ev)
        else:
            self.check.toggle()

    def editors(self) -> list:
        return [self.check]

    def set_value(self, v) -> None:
        self.check.blockSignals(True)
        self.check.setChecked(bool(v))
        self.check.blockSignals(False)


class ChildrenEdit(Bound):
    """List of children (birth year, Kindergeld) with adding and removing; value = [(geburtsjahr, kindergeld)]."""

    def __init__(self, path, label, lo: int, hi: int, tooltip=""):
        super().__init__(path, label, tooltip)
        self.lo, self.hi = lo, hi
        self._value: list = []
        box = QWidget()
        self.grid = QGridLayout(box)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(8)
        self.add_editor(box)
        self.add_btn = QPushButton("+ Kind hinzufügen")
        self.add_btn.clicked.connect(self._add_child)
        self._lay.addWidget(self.add_btn, 2, 1, Qt.AlignmentFlag.AlignLeft)
        self.rows: list[tuple] = []

    def editors(self) -> list:
        return [self.add_btn] + [w for r in self.rows for w in r[1:]]

    def set_value(self, v) -> None:
        self._value = [(int(gj), bool(kg)) for gj, kg in v]
        for r in self.rows:
            for w in r:
                self.grid.removeWidget(w)
                w.deleteLater()
        self.rows = []
        if not self._value:
            empty = QLabel("<i>keine Kinder</i>")
            self.grid.addWidget(empty, 0, 0)
            self.rows.append((empty,))
        for n, (gj, kg) in enumerate(self._value):
            lbl = QLabel(f"Kind {n + 1}")
            spin = QSpinBox()
            spin.setRange(min(self.lo, gj), max(self.hi, gj))
            spin.setValue(gj)
            spin.setKeyboardTracking(False)
            spin.setToolTip("Geburtsjahr")
            spin.setMinimumWidth(75)
            spin.valueChanged.connect(lambda y, n=n: self._edit(n, year=int(y)))
            check = QCheckBox("Kindergeld")
            check.setChecked(kg)
            check.setToolTip("Kindergeldbezug (Kinderfreibeträge, Günstigerprüfung, ALG-Leistungssatz)")
            check.toggled.connect(lambda b, n=n: self._edit(n, kg=bool(b)))
            rm = QToolButton()
            rm.setText("✕")
            rm.setToolTip("Kind entfernen")
            rm.clicked.connect(lambda _=False, n=n: self._remove(n))
            for col, w in enumerate((lbl, spin, check, rm)):
                self.grid.addWidget(w, n, col)
            self.rows.append((lbl, spin, check, rm))
        self.grid.setColumnStretch(4, 1)

    def _changed(self, v: list) -> None:
        self.set_value(v)
        self._emit(list(self._value))

    def _edit(self, n: int, year: int | None = None, kg: bool | None = None) -> None:
        v = list(self._value)
        gj, k = v[n]
        v[n] = (year if year is not None else gj, kg if kg is not None else k)
        self._value = v  # no rebuild: keeps the focus in the spin box
        self._emit(list(v))

    def _add_child(self) -> None:
        self._changed(self._value + [(self.hi, True)])

    def _remove(self, n: int) -> None:
        self._changed(self._value[:n] + self._value[n + 1:])


class TextEdit(Bound):
    """Single-line text (committed when editing is finished)."""

    def __init__(self, path, label, tooltip="", placeholder=""):
        super().__init__(path, label, tooltip)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.edit.editingFinished.connect(lambda: self._emit(self.edit.text().strip()))
        self.add_editor(self.edit)

    def editors(self) -> list:
        return [self.edit]

    def set_value(self, v) -> None:
        self.edit.blockSignals(True)
        self.edit.setText(str(v or ""))
        self.edit.blockSignals(False)
