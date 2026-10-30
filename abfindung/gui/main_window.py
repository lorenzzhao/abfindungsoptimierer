# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Main window: inputs | results + charts | explanation."""

from __future__ import annotations

import time
import traceback
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QLabel, QMainWindow, QMessageBox, QPushButton,
                             QMenu, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from .. import DISCLAIMER
from ..engine.scenario import run
from ..engine.settings import from_personal, to_personal
from ..io import ValidationError, load_legal, load_personal
from ..io.personal_writer import save_personal
from . import theme as themes
from .chart_panel import ChartPanel
from .explain_panel import ExplainPanel
from .inputs_panel import InputsPanel
from .optimizer_dialog import OptimizerDialog
from .results_panel import ResultsPanel

EXAMPLES = Path(__file__).resolve().parent.parent.parent / "examples"
TEMPLATE = Path(__file__).resolve().parent.parent / "resources" / "vorlage_persoenlich.xml"  # Datei → Neu


class MainWindow(QMainWindow):
    def __init__(self, personal_path: str | None = None, legal_path: str | None = None, dark: bool | None = None):
        super().__init__()
        self.qs = QSettings("abfindungsoptimierer", "gui")
        self.pd = None
        self.legal = None
        self.s = None
        self.res = None
        self.personal_path = None
        self.legal_path = None
        self.dirty = False
        self.migrated = False
        self.opt_top = None

        app = QApplication.instance()
        if dark is None:
            stored = self.qs.value("dark")
            dark = (stored == "true") if stored is not None else themes.system_prefers_dark(app)
        self.theme = themes.apply(app, dark)

        self.inputs = InputsPanel()
        self.results = ResultsPanel()
        self.charts = ChartPanel()
        self.explain = ExplainPanel()
        mid = QSplitter(Qt.Orientation.Vertical)
        mid.addWidget(self.results)
        mid.addWidget(self.charts)
        mid.setSizes([380, 420])
        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(self.inputs)
        split.addWidget(mid)
        split.addWidget(self.explain)
        split.setSizes([450, 600, 430])
        central = QWidget()
        v = QVBoxLayout(central)
        v.setContentsMargins(4, 4, 4, 4)
        self.disclaimer = QLabel(f"<b>Hinweis:</b> {DISCLAIMER}")
        self.disclaimer.setWordWrap(True)
        self.disclaimer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._style_disclaimer()
        v.addWidget(self.disclaimer)
        v.addWidget(split, 1)
        self.setCentralWidget(central)
        self.status = QLabel()
        self.statusBar().addWidget(self.status, 1)

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self._recalc_when_released)
        # undo / redo: one step = all changes until a short pause (e.g. dragging a slider)
        self.undo_stack: list = []
        self.redo_stack: list = []
        self._snapshot = None
        self._restoring = False
        self.group_timer = QTimer(self)
        self.group_timer.setSingleShot(True)
        self.group_timer.setInterval(800)
        self.group_timer.timeout.connect(self._end_group)

        self.inputs.settingsChanged.connect(self._changed)
        self.results.focusChanged.connect(self._focus_changed)
        self.explain.focusRequested.connect(self.results.set_focus)
        self.charts.focusRequested.connect(self.results.set_focus)
        self._actions()
        self.results.set_colors(self.theme.html)
        self.resize(1500, 900)
        self._load_initial(personal_path, legal_path)

    # -- actions --------------------------------------------------------------------
    def _actions(self) -> None:
        def act(text, slot, shortcut=None, checkable=False):
            a = QAction(text, self)
            a.triggered.connect(slot)
            if shortcut:
                a.setShortcut(QKeySequence(shortcut))
            a.setCheckable(checkable)
            return a

        self.a_new = act("Neu (leere Vorlage)", self.new_personal, QKeySequence.StandardKey.New)
        self.a_open_p = act("Persönliche Daten öffnen …", self.open_personal, "Ctrl+O")
        self.a_open_l = act("Rechtliche Vorgaben öffnen …", self.open_legal, "Ctrl+Shift+O")
        self.a_save = act("Speichern", self.save, QKeySequence.StandardKey.Save)
        self.a_save_as = act("Speichern unter …", self.save_as, QKeySequence.StandardKey.SaveAs)
        self.a_pdf = act("PDF exportieren …", self.export_pdf, "Ctrl+P")
        self.a_changes = act("Änderungen seit dem Speichern …", self.show_changes)
        self.a_opt = act("Optimieren …", self.optimize, "Ctrl+R")
        self.a_legal_prompt = act("KI-Prompt zur Prüfung der rechtlichen Vorgaben …", self.legal_prompt)
        self.a_undo = act("Rückgängig", self.undo, QKeySequence.StandardKey.Undo)
        self.a_redo = act("Wiederholen", self.redo, QKeySequence.StandardKey.Redo)
        self.a_undo.setToolTip("Letzte Änderung rückgängig machen (Strg+Z)")
        self.a_redo.setToolTip("Rückgängig gemachte Änderung wiederholen (Strg+Y)")
        self.a_dark = act("Dunkelmodus", self.toggle_dark, checkable=True)
        self.a_dark.setChecked(self.theme.dark)
        self.a_quit = act("Beenden", self.close, QKeySequence.StandardKey.Quit)
        m = self.menuBar().addMenu("&Datei")
        self.recent_menu = QMenu("Zuletzt verwendete persönliche Daten", self)
        self.recent_menu.aboutToShow.connect(self._fill_recent_menu)
        for a in (self.a_new, self.a_open_p, self.recent_menu, self.a_open_l, None, self.a_save, self.a_save_as,
                  self.a_changes, None, self.a_pdf, None, self.a_quit):
            if a is None:
                m.addSeparator()
            elif isinstance(a, QMenu):
                m.addMenu(a)
            else:
                m.addAction(a)
        m = self.menuBar().addMenu("&Bearbeiten")
        m.addAction(self.a_undo)
        m.addAction(self.a_redo)
        m.addSeparator()
        m.addAction(self.a_changes)
        m = self.menuBar().addMenu("&Analyse")
        m.addAction(self.a_opt)
        m.addSeparator()
        m.addAction(self.a_legal_prompt)
        m = self.menuBar().addMenu("&Ansicht")
        m.addAction(self.a_dark)
        m = self.menuBar().addMenu("&Hilfe")
        m.addAction(act("Über …", self.about))
        self._update_undo_actions()

    # -- loading -----------------------------------------------------------------------
    def _load_initial(self, personal_path, legal_path) -> None:
        lp = legal_path or self.qs.value("legal_path") or str(EXAMPLES / "gesetzliche_vorgaben_beispiel.xml")
        pp = personal_path or self.qs.value("personal_path")
        if not Path(lp).exists():
            lp = str(EXAMPLES / "gesetzliche_vorgaben_beispiel.xml")
        if pp and Path(pp).exists():
            self._load(pp, lp)
        else:  # first start or file moved: start with the empty template
            self._load(None, lp)
            self._load_template()

    def _load_template(self) -> bool:
        """New personal data from the template; the first save asks for a file name."""
        if not self._load(str(TEMPLATE), None):
            return False
        self.personal_path = None
        self.qs.remove("personal_path")
        self._update_title()
        return True

    def new_personal(self) -> None:
        if self._maybe_save():
            self._load_template()

    def _load(self, personal_path: str | None, legal_path: str | None) -> bool:
        try:
            legal = load_legal(legal_path) if legal_path else self.legal
            pd = load_personal(personal_path) if personal_path else self.pd
        except ValidationError as e:
            QMessageBox.critical(self, "Datei ungültig", e.pretty())
            return False
        if legal is not None and pd is None:  # rules loaded first, personal data follows (template)
            self.legal = legal
            if legal_path:
                self.legal_path = legal_path
                self.qs.setValue("legal_path", legal_path)
            return True
        if legal is None or pd is None:
            return False
        try:
            s = from_personal(pd, legal)
        except Exception as e:  # missing parameter etc.
            QMessageBox.critical(self, "Fehler beim Einlesen", f"{e}\n\n{traceback.format_exc(limit=3)}")
            return False
        self.legal, self.pd, self.s = legal, pd, s
        if legal_path:
            self.legal_path = legal_path
            self.qs.setValue("legal_path", legal_path)
        if personal_path:
            self.personal_path = personal_path
            self.qs.setValue("personal_path", personal_path)
            if Path(personal_path).resolve() != TEMPLATE.resolve():
                self._remember_recent(personal_path)
        self.migrated = bool(pd.migration_notes)  # converted values should be saved
        self.dirty = self.migrated
        self.opt_top = None
        self.inputs.load(s, legal)
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.group_timer.stop()
        self._snapshot = s.copy()
        self._update_undo_actions()
        self.recalc()
        if pd.migration_notes:
            QMessageBox.information(self, "Ältere Datei übernommen", "\n".join(pd.migration_notes))
        return True

    # -- recently used personal data -----------------------------------------------------
    RECENT_MAX = 8

    def recent_files(self) -> list[str]:
        value = self.qs.value("recent_personal") or []
        return [value] if isinstance(value, str) else [str(v) for v in value]

    def _remember_recent(self, path: str) -> None:
        path = str(Path(path).resolve())
        files = [path] + [f for f in self.recent_files() if f != path]
        self.qs.setValue("recent_personal", files[:self.RECENT_MAX])

    def _fill_recent_menu(self) -> None:
        self.recent_menu.clear()
        files = self.recent_files()
        if not files:
            self.recent_menu.addAction("(noch keine)").setEnabled(False)
            return
        for i, f in enumerate(files, 1):
            exists = Path(f).exists()
            a = self.recent_menu.addAction(f"&{i} {Path(f).name}" + ("" if exists else " (nicht gefunden)"))
            a.setToolTip(f)
            a.setStatusTip(f)
            a.setEnabled(exists)
            a.triggered.connect(lambda _=False, f=f: self.open_recent(f))
        self.recent_menu.addSeparator()
        self.recent_menu.addAction("Liste leeren", lambda: self.qs.remove("recent_personal"))

    def open_recent(self, path: str) -> None:
        if self._maybe_save():
            self._load(path, None)

    def open_personal(self) -> None:
        if not self._maybe_save():
            return
        f, _ = QFileDialog.getOpenFileName(self, "Persönliche Daten öffnen", str(Path(self.personal_path).parent if self.personal_path else Path.home()),
                                           "XML (*.xml)")
        if f:
            self._load(f, None)

    def open_legal(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, "Rechtliche Vorgaben öffnen", str(Path(self.legal_path or EXAMPLES).parent),
                                           "XML (*.xml)")
        if f:
            self._load(None, f)

    # -- calculation ------------------------------------------------------------------
    def _changed(self) -> None:
        # unsaved = differs from the last loaded / saved state (or an older file was converted on load)
        self.dirty = self.inputs.has_changes() or self.migrated
        self._update_title()
        if not self._restoring and self._snapshot is not None:
            if not self.group_timer.isActive():  # first change of a new step: remember the state before it
                self.undo_stack.append(self._snapshot)
                self.redo_stack.clear()
            self.group_timer.start()
            self._update_undo_actions()
        self.timer.start()

    # -- undo / redo ---------------------------------------------------------------------
    def _end_group(self) -> None:
        self.group_timer.stop()
        self._snapshot = self.s.copy() if self.s else None

    def _update_undo_actions(self) -> None:
        self.a_undo.setEnabled(bool(self.undo_stack))
        self.a_redo.setEnabled(bool(self.redo_stack))

    def undo(self) -> None:
        if self.group_timer.isActive():
            self._end_group()
        if not self.undo_stack:
            return
        self.redo_stack.append(self.s.copy())
        self._restore(self.undo_stack.pop())

    def redo(self) -> None:
        if self.group_timer.isActive():
            self._end_group()
        if not self.redo_stack:
            return
        self.undo_stack.append(self.s.copy())
        self._restore(self.redo_stack.pop())

    def _restore(self, state) -> None:
        """Show a previous state of all inputs (values, origins, area switches)."""
        self._restoring = True
        try:
            same_layout = (self.s.years() == state.years() and self.s.familienstand == state.familienstand
                           and len(self.s.persons) == len(state.persons)
                           and self.s.measures.items.keys() == state.measures.items.keys())
            self.s = state
            self.inputs.s = state
            if same_layout:
                self.inputs.refresh()  # keeps the scroll position
            else:
                self.inputs.rebuild()  # other horizon: other year rows
            self._snapshot = state.copy()
            self.dirty = self.inputs.has_changes() or self.migrated
            self._update_title()
            self.recalc()
        finally:
            self._restoring = False
        self._update_undo_actions()

    def _recalc_when_released(self) -> None:
        """Wait while a mouse button is held on a spin box: the recalculation blocks the event loop for a
        moment, and Qt's auto-repeat of the arrow buttons would otherwise add a second step."""
        if self.inputs.wheel_guard.spin_held:
            self.timer.start()
            return
        self.recalc()

    def recalc(self) -> None:
        if not self.s:
            return
        t0 = time.perf_counter()
        try:
            self.res = run(self.s, self.legal)
        except Exception as e:
            self.status.setText(f"Fehler in der Berechnung: {e}")
            traceback.print_exc()
            return
        ms = (time.perf_counter() - t0) * 1000
        o = self.s.options
        if o.horizon_auto and (o.horizon_start, o.horizon_end) != (self.res.years[0], self.res.years[-1]):
            # keep the input ranges (salary years, payment month, assessment per year) in line with the horizon
            o.horizon_start, o.horizon_end = self.res.years[0], self.res.years[-1]
            self.inputs.rebuild()
        self.results.update_results(self.res)
        self.inputs.set_result(self.res)
        self.charts.set_data(self.res, self.legal, self.results.focus_id, self.theme.chart)
        self.explain.show_result(self.res, self.results.focus_id, self.theme.html)
        warn_legal = ""
        if not self.legal.pick("rv_beitragssatz_gesamt", "rv_beitragssatz"):
            warn_legal = " · ⚠ rv_beitragssatz_gesamt fehlt in den rechtlichen Vorgaben"
        self.status.setText(f"Persönlich: {Path(self.personal_path).name if self.personal_path else '–'} · "
                            f"Rechtlich: {Path(self.legal_path).name if self.legal_path else '–'} "
                            f"(Stand {self.legal.stand}) · beide gegen XSD validiert · Berechnung {ms:.0f} ms{warn_legal}")
        self._update_title()

    def _focus_changed(self, fid: str) -> None:
        self.explain.show_result(self.res, fid, self.theme.html)
        self.charts.set_focus(fid)

    # -- optimisation ------------------------------------------------------------------
    def legal_prompt(self) -> None:
        """Prompt for checking the loaded legal rules in an AI chat (no personal data)."""
        from ..legal_prompt import build_prompt
        from .legal_prompt_dialog import LegalPromptDialog

        if self.legal is None:
            return
        used = sorted({k.split("@")[0] for k in self.res.tracer.used_params}) if self.res and self.res.tracer else []
        years = self.res.years if self.res else []
        LegalPromptDialog(build_prompt(self.legal, years, used), self.legal.path, self).exec()

    def optimize(self) -> None:
        if not self.s:
            return
        dlg = OptimizerDialog(self.s, self.legal, self)
        dlg.applyRequested.connect(self._apply_candidate)
        dlg.topReady.connect(self.set_optimizer_top)
        dlg.show()

    def set_optimizer_top(self, top) -> None:
        self.opt_top = top

    def _apply_candidate(self, changes: dict) -> None:
        self.inputs.apply_changes(changes)
        self.results.set_focus("saldo")

    # -- saving / export ---------------------------------------------------------------
    def _write(self, path: str, backup: bool) -> bool:
        try:
            data = to_personal(self.s, self.pd)
            save_personal(data, path, backup=backup)
        except ValidationError as e:
            QMessageBox.critical(self, "Export ungültig", e.pretty())
            return False
        except OSError as e:
            QMessageBox.critical(self, "Speichern fehlgeschlagen", str(e))
            return False
        self.pd = data
        self.personal_path = path
        self.qs.setValue("personal_path", path)
        self._remember_recent(path)
        self.migrated = False
        self.inputs.mark_saved()
        self.dirty = False
        self._update_title()
        self.statusBar().showMessage(f"Gespeichert und gegen das Schema validiert: {path}", 6000)
        return True

    def save(self) -> bool:
        if not self.personal_path or Path(self.personal_path).resolve().parent == EXAMPLES.resolve():  # template / example
            return self.save_as()
        return self._write(self.personal_path, backup=True)

    def save_as(self) -> bool:
        start = self.personal_path or str(Path.home() / "persoenliche_daten.xml")
        f, _ = QFileDialog.getSaveFileName(self, "Persönliche Daten speichern unter", start, "XML (*.xml)")
        if not f:
            return False
        if not f.lower().endswith(".xml"):
            f += ".xml"
        return self._write(f, backup=True)

    def show_changes(self) -> None:
        """List of values (and origins) that differ from the last loaded / saved XML."""
        from ..io.personal_model import HERKUNFT_LABEL
        from ..report.inputs_table import fmt_path_value

        rows = self.inputs.changes()
        dlg = QDialog(self)
        dlg.setWindowTitle("Änderungen seit dem Speichern")
        dlg.resize(820, 420)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(f"{len(rows)} Änderung(en) gegenüber der zuletzt geladenen bzw. gespeicherten Datei. "
                             "Strg + Klick auf den Punkt ● am Wert setzt ihn zurück." if rows else
                             "Keine Änderungen – die Eingaben entsprechen der XML-Datei."))
        if rows:
            t = QTableWidget(len(rows), 5)
            t.setHorizontalHeaderLabels(["Bereich", "Wert", "gespeichert", "aktuell", "Herkunft"])
            t.verticalHeader().setVisible(False)
            t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            for r, (path, lab, tab, v0, v1, o0, o1) in enumerate(rows):
                herk = HERKUNFT_LABEL.get(o1, o1) if o0 == o1 else f"{HERKUNFT_LABEL.get(o0, o0)} → {HERKUNFT_LABEL.get(o1, o1)}"
                for col, txt in enumerate((tab, lab, fmt_path_value(path, v0), fmt_path_value(path, v1), herk)):
                    t.setItem(r, col, QTableWidgetItem(str(txt)))
            t.resizeColumnsToContents()
            lay.addWidget(t, 1)
        close = QPushButton("Schließen")
        close.clicked.connect(dlg.accept)
        lay.addWidget(close)
        dlg.exec()

    def export_pdf(self) -> None:
        if not self.res:
            return
        start = str(Path(self.personal_path or Path.home()).with_suffix("")) + "_bericht.pdf"
        f, _ = QFileDialog.getSaveFileName(self, "PDF exportieren", start, "PDF (*.pdf)")
        if not f:
            return
        from ..report.pdf_export import export_pdf

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            export_pdf(f, self.res, self.legal, focus_id=self.results.focus_id, optimizer_top=self.opt_top,
                       personal_path=self.personal_path, legal_path=self.legal_path)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "PDF-Export fehlgeschlagen", f"{e}\n\n{traceback.format_exc(limit=4)}")
            return
        QApplication.restoreOverrideCursor()
        self.statusBar().showMessage(f"PDF exportiert: {f}", 8000)

    # -- misc ------------------------------------------------------------------------
    def _style_disclaimer(self) -> None:
        fg, bg = ("#ff8a80", "#3a1414") if self.theme.dark else ("#b00020", "#fdecea")
        self.disclaimer.setStyleSheet(f"QLabel {{color:{fg}; background:{bg}; border:1px solid {fg}; "
                                      "border-radius:3px; padding:4px; font-size:10pt;}")

    def toggle_dark(self, on: bool) -> None:
        self.theme = themes.apply(QApplication.instance(), on)
        self._style_disclaimer()
        self.qs.setValue("dark", "true" if on else "false")
        self.results.set_colors(self.theme.html)
        if self.res:
            self.charts.set_data(self.res, self.legal, self.results.focus_id, self.theme.chart)
            self.explain.show_result(self.res, self.results.focus_id, self.theme.html)

    def about(self) -> None:
        from .about_dialog import AboutDialog

        AboutDialog(self).exec()

    def _update_title(self) -> None:
        name = Path(self.personal_path).name if self.personal_path else "neu, noch nicht gespeichert"
        self.setWindowTitle(f"Abfindungsoptimierer – {name}{' *' if self.dirty else ''}")

    def _maybe_save(self) -> bool:
        if not self.dirty:
            return True
        r = QMessageBox.question(self, "Ungespeicherte Änderungen", "Änderungen an den Stellschrauben speichern?",
                                 QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                                 | QMessageBox.StandardButton.Cancel)
        if r == QMessageBox.StandardButton.Save:
            return self.save()
        return r == QMessageBox.StandardButton.Discard

    def closeEvent(self, ev) -> None:
        if self._maybe_save():
            ev.accept()
        else:
            ev.ignore()
