# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Optimisation dialog: runs the search in a background thread and shows the top 5."""

from __future__ import annotations

from html import escape

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QDoubleSpinBox, QHBoxLayout, QLabel, QProgressBar,
                             QPushButton, QTableWidget, QTableWidgetItem, QTextBrowser, QVBoxLayout)

from ..dates import fmt_eur
from ..engine.optimizer import fixed_values, optimize


class Worker(QThread):
    progress = Signal(int, int)
    done = Signal(object, object)
    failed = Signal(str)

    def __init__(self, s, legal, opt_br, opt_erh):
        super().__init__()
        self.s, self.legal, self.opt_br, self.opt_erh = s, legal, opt_br, opt_erh
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            top, cur = optimize(self.s, self.legal, self.opt_br, self.opt_erh,
                                progress=lambda k, n: self.progress.emit(k, n), should_stop=lambda: self._stop)
            self.done.emit(top, cur)
        except Exception as exc:  # pragma: no cover - shown to the user
            self.failed.emit(str(exc))


class OptimizerDialog(QDialog):
    applyRequested = Signal(dict)
    topReady = Signal(list)

    def __init__(self, settings, legal, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Optimierung")
        self.resize(980, 640)
        self.s, self.legal = settings.copy(), legal
        self.top = []
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(
            "Durchsucht Zahlungsjahre der Abfindung (je Jahr der KV-günstigste Monat) und Meldedaten vollständig. "
            "Die Basisrente wird je Jahr bis zur Nullgrenze vorgeschlagen (gedeckelt durch den Höchstbetrag; ohne Eintrag "
            "im Jahr entsteht beim Übernehmen ein neuer). Erhaltungsaufwand-Einträge mit Herkunft „Planung“ werden per "
            "goldenem Schnitt optimiert. Die Veranlagungsart wählt die Berechnung je Jahr. "
            "Zielgröße ist der Saldo."))
        fixed = fixed_values(self.s, legal)
        fx = QLabel("<small><b>Bleibt fest</b> (Herkunft ≠ Planung, per Klick auf das Herkunfts-Badge änderbar): "
                    + (", ".join(fixed) if fixed else "nichts – alle Optimierungsgrößen sind „Planung“") + "</small>")
        fx.setWordWrap(True)
        lay.addWidget(fx)
        h = QHBoxLayout()
        self.cb_br = QCheckBox("Basisrente je Jahr bis zur Nullgrenze")
        self.cb_br.setChecked(True)
        if not self.s.active("gestaltungen"):  # disabled area: measures are not optimised
            self.cb_br.setChecked(False)
            self.cb_br.setEnabled(False)
        self.cb_erh = QCheckBox("Erhaltungsaufwand-Einträge optimieren bis")
        self.erh_max = QDoubleSpinBox()
        self.erh_max.setRange(0, 500_000)
        self.erh_max.setSingleStep(1000)
        self.erh_max.setSuffix(" €")
        self.erh_max.setValue(self.s.erhaltung_max)
        self.cb_erh.setEnabled(self.s.active("gestaltungen"))
        self.btn_start = QPushButton("Optimierung starten")
        self.btn_start.clicked.connect(self.start)
        for w in (self.cb_br, self.cb_erh, self.erh_max):
            h.addWidget(w)
        h.addStretch(1)
        h.addWidget(self.btn_start)
        lay.addLayout(h)
        self.bar = QProgressBar()
        lay.addWidget(self.bar)
        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(["Rang", "Saldo", "Δ zu aktuell", "Steuer je Jahr", "ALG", "eigene KV",
                                              "Gegenwert", "Liq.-Tiefpunkt"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._selected)
        lay.addWidget(self.table, 1)
        self.text = QTextBrowser()
        lay.addWidget(self.text, 1)
        hb = QHBoxLayout()
        self.btn_apply = QPushButton("Ausgewählte Kombination übernehmen")
        self.btn_apply.setEnabled(False)
        self.btn_apply.clicked.connect(self._apply)
        close = QPushButton("Schließen")
        close.clicked.connect(self.close)
        hb.addStretch(1)
        hb.addWidget(self.btn_apply)
        hb.addWidget(close)
        lay.addLayout(hb)
        self.worker = None

    def start(self):
        self.s.erhaltung_max = self.erh_max.value()
        self.btn_start.setEnabled(False)
        self.table.setRowCount(0)
        self.text.setHtml("<p>Berechnung läuft …</p>")
        self.worker = Worker(self.s, self.legal, self.cb_br.isChecked(), self.cb_erh.isChecked())
        self.worker.progress.connect(lambda k, n: (self.bar.setMaximum(n), self.bar.setValue(k)))
        self.worker.done.connect(self._done)
        self.worker.failed.connect(lambda m: self.text.setPlainText("Fehler: " + m))
        self.worker.start()

    def _done(self, top, cur):
        self.top, self.cur = top, cur
        self.bar.setValue(self.bar.maximum())
        self.btn_start.setEnabled(True)
        self.table.setRowCount(len(top))
        for i, c in enumerate(top):
            vals = [str(i + 1), fmt_eur(c.saldo), fmt_eur(c.saldo - cur.saldo),
                    ", ".join(f"{y}: {fmt_eur(v)}" for y, v in sorted(c.tax_by_year.items())), fmt_eur(c.alg),
                    fmt_eur(c.kv), fmt_eur(c.gebunden), fmt_eur(c.liq_min)]
            for j, v in enumerate(vals):
                self.table.setItem(i, j, QTableWidgetItem(v))
        self.table.resizeColumnsToContents()
        h = cur.extra.get("horizont")
        if h:
            self.bar.setFormat(f"fertig – Salden einheitlich über {h[0]}–{h[1]} verglichen")
        if top:
            self.table.selectRow(0)
        self.topReady.emit(top)

    def _selected(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        c = self.top[rows[0].row()]
        self.btn_apply.setEnabled(True)
        html = f"<h3>Warum ist das besser?</h3><p>{escape(c.label)}</p><ul>"
        html += "".join(f"<li>{escape(line)}</li>" for line in c.explanation.splitlines())
        html += "</ul>"
        if c.rules:
            html += "<p><b>Beteiligte Regeln:</b> " + ", ".join(
                f"{escape(r)} ({escape(self.legal.rule(r).bezeichnung) if self.legal.rule(r) else ''})" for r in c.rules) + "</p>"
        self.text.setHtml(html)

    def _apply(self):
        rows = self.table.selectionModel().selectedRows()
        if rows:
            self.applyRequested.emit(self.top[rows[0].row()].changes)

    def closeEvent(self, ev):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(5000)
        super().closeEvent(ev)
