# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Area 1: the adjustable inputs (Stellschrauben), grouped in tabs."""

from __future__ import annotations

from datetime import date
import copy
from html import escape

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QActionGroup, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (QCheckBox, QComboBox, QGroupBox, QHBoxLayout, QLabel, QMenu, QPushButton, QScrollArea,
                             QSpinBox,
                             QTabWidget,
                             QVBoxLayout, QWidget)

from ..dates import fmt_eur, month_index
from ..engine.settings import (GESTALTUNG_TYPEN, Settings, add_gestaltung, allowed_origins, apply_exit, gestaltungen,
                               is_program_derived, remove_gestaltung, set_basisrente_year, set_familienstand,
                               set_salary_mode)
from ..io.personal_model import HERKUNFT_LABEL
from ..report.inputs_table import fmt_path_value
from .widgets import (CHANGED_COLOR, BoolEdit, Bound, ChildrenEdit, ChoiceEdit, DateEdit, IntEdit, MonthEdit, NumberEdit,
                      TextEdit, WheelGuard, compact_combo)

FAMILIENSTAND = [("verheiratet", "verheiratet"), ("ledig", "ledig"), ("geschieden", "geschieden"), ("verwitwet", "verwitwet")]
BUNDESLAENDER = ["BW", "BY", "BE", "BB", "HB", "HH", "HE", "MV", "NI", "NW", "RP", "SL", "SN", "ST", "SH", "TH"]


def refs_tooltip(legal, rules=(), params=(), text: str = "") -> str:
    """Rich-text tooltip with rule descriptions, paragraphs and source links."""
    parts = []
    if text:
        parts.append(f"<p>{escape(text)}</p>")
    for rid in rules:
        r = legal.rule(rid)
        if not r:
            continue
        srcs = []
        for q in r.quellen:
            src = legal.source(q.quelle)
            url = f" – {escape(src.url)}" if src and src.url else ""
            srcs.append(f"{escape(q.text)}{url}")
        parts.append(f"<p><b>{escape(rid)}</b>: {escape(r.bezeichnung)}<br/><small>{escape(r.beschreibung)}</small>"
                     f"<br/><small><i>{'<br/>'.join(srcs)}</i></small></p>")
    for pid in params:
        if legal.has(pid):
            p = legal.param(pid)
            parts.append(f"<p><code>{escape(pid)}</code> = {escape(p.entry.raw)} {escape(p.entry.einheit)}<br/>"
                         f"<small>{escape(p.entry.bezeichnung)}</small></p>")
    return "<qt>" + "".join(parts) + "</qt>" if parts else ""


ANNUAL_EQUIV_TIP = (
    "<qt><b>Warum das hochgerechnete Jahresgehalt wichtig ist</b><br/>"
    "Mehrere Regeln brauchen das Gehalt einer vollen Beschäftigung, nicht den im Jahr gezahlten Betrag:"
    "<ul>"
    "<li><b>Ruhen nach § 158 SGB III</b> (R_Ruhen158): Der anrechenbare Teil der Abfindung wird durch das "
    "kalendertägliche Arbeitsentgelt geteilt; daraus folgt, wie lange das ALG ruht.</li>"
    "<li><b>Zusammenballung</b> (R_Zusammenballung): Die Fünftelregelung setzt voraus, dass die Einkünfte im "
    "Zuflussjahr höher sind als bei Fortsetzung des Arbeitsverhältnisses – verglichen wird mit dem Jahresgehalt.</li>"
    "<li><b>ALG-Höhe</b> (R_ALG_Hoehe, eigene Berechnung): Bemessungsentgelt aus den letzten 12 Monaten.</li>"
    "<li><b>Monatsgehalt</b> für Zeitleiste, KV-Arbeitnehmeranteil und Rentenversicherung.</li>"
    "</ul>Hochrechnung: gezahlter Betrag × 12 / gearbeitete Monate.</qt>"
)


ORIGIN_HELP = {
    "angabe": "Gesicherter Wert: von dir angegeben oder belegt (z. B. Vertrag, Gehaltsabrechnung, Steuerbescheid). "
              "Bleibt bei der Optimierung fest.",
    "annahme": "Unsicherer Wert: geschätzt oder unterstellt, bitte prüfen. Abhängige Ergebnisse werden mit „≈“ "
               "markiert. Bleibt bei der Optimierung fest.",
    "planung": "Stellschraube, die du noch frei wählen kannst. Der Optimierer darf diesen Wert verändern.",
    "abgeleitet": "Aus anderen Angaben hergeleitet (z. B. aus einer Regel oder einem anderen Wert). "
                  "Bleibt bei der Optimierung fest.",
    "berechnet": "Ergebnis einer Berechnung (z. B. einer früheren Überschlagsrechnung). Bleibt bei der Optimierung fest.",
    "illustrativ": "Rechenbeispiel ohne konkreten Plan. Bleibt bei der Optimierung fest.",
}


DERIVED_HELP = ("Das Programm bestimmt diesen Wert selbst aus den übrigen Werten und den rechtlichen Regeln. "
                "Das Eingabefeld ist dann gesperrt; der Tooltip am Wert erklärt die Herleitung.")


def _red_dot_icon() -> QIcon:
    """Small red dot for tabs that contain changes (tab texts cannot be coloured partially)."""
    pm = QPixmap(10, 10)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(CHANGED_COLOR))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(1, 1, 8, 8)
    p.end()
    return QIcon(pm)


class InputsPanel(QWidget):
    settingsChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.s: Settings | None = None
        self.legal = None
        self.controls: list[Bound] = []
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        title = QLabel("<b>Stellschrauben</b> <small>(Werte per Mausrad nur mit gedrückter Strg-Taste; "
                       "Strg + Klick auf Label, Herkunft oder <span style='color:#d32f2f'>●</span> setzt auf den "
                       "gespeicherten Stand zurück)</small>")
        title.setWordWrap(True)
        self.wheel_guard = WheelGuard(self)
        lay.addWidget(title)
        lay.addWidget(self.tabs)
        self.extra = {}

    # -- building ------------------------------------------------------------------
    def load(self, s: Settings, legal) -> None:
        self.s, self.legal = s, legal
        self.baseline = {}
        self.rebuild()
        self.mark_saved()

    def rebuild(self) -> None:
        cur = self.tabs.currentIndex()
        self.tabs.clear()
        self.controls = []
        s = self.s
        self.sections: dict[str, tuple] = {}
        self.dependent: list = []
        self.salary_rows: dict[int, list] = {}
        self.tab_titles: list[str] = []
        self.tab_paths: list[set] = []  # setting paths shown in each tab (for the change marker in the title)

        def add_tab(build, title, section=None, text=None):
            n = len(self.controls)
            w = build()
            if section:
                w = self._section(section, w, text) if text else self._section(section, w)
            self.tabs.addTab(self._scroll(w), title)
            self.tab_titles.append(title)
            self.tab_paths.append({c.path for c in self.controls[n:]} | ({f"sections.{section}"} if section else set()))

        for i, ps in enumerate(s.persons[:2 if s.married else 1]):  # the spouse only when married
            add_tab(lambda i=i: self._person_tab(i), ps.label)
        add_tab(self._household_tab, "Haushalt", "haushalt")
        add_tab(self._kv_tab, "KV", "kv")
        add_tab(self._measures_tab, "Gestaltungen", "gestaltungen")
        self.tab_paths[-1].add("gestaltungen")
        add_tab(self._options_tab, "Optionen", "optionen")
        if 0 <= cur < self.tabs.count():
            self.tabs.setCurrentIndex(cur)
        self.wheel_guard.install(self.tabs)
        self.refresh()

    def _section(self, key: str, content: QWidget, text: str = "Bereich in Berechnung und Optimierung einbeziehen") -> QWidget:
        """Optional area: a check box on top; when off, the content is greyed out and ignored by the
        calculation (values are still read from / written to the XML)."""
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        check = QCheckBox(text)
        f = check.font()
        f.setBold(True)
        check.setFont(f)
        check.setToolTip("Deaktiviert: Werte bleiben erhalten und werden gespeichert, gehen aber nicht in "
                         "Berechnung und Optimierung ein.")
        check.toggled.connect(lambda on, k=key: self._toggle_section(k, on))
        v.addWidget(check)
        v.addWidget(content, 1)
        self.sections[key] = (check, content, box)
        return box

    def _toggle_section(self, key: str, on: bool) -> None:
        self.s.set(f"sections.{key}", bool(on))
        self._show_section(key)
        self._update_changes()
        self.settingsChanged.emit()

    def locations(self) -> list[dict]:
        """Every input field with where it is in the program (tab › group › label), its settings and XML path,
        its value and origin and whether it takes part in the calculation (for the review prompt)."""
        out = []
        for key, (check, _content, _box) in self.sections.items():
            tab = next((t for t, ps in zip(self.tab_titles, self.tab_paths) if f"sections.{key}" in ps), "")
            out.append(dict(path=f"sections.{key}", tab=tab, groups=[], label=check.text(), value=check.isChecked(),
                            origin="angabe", xml="", active=True))
        for c in self.controls:
            tab = next((t for t, ps in zip(self.tab_titles, self.tab_paths) if c.path in ps), "")
            groups, w = [], c.parentWidget()
            while w is not None and w is not self:
                if isinstance(w, QGroupBox) and w.title():
                    groups.insert(0, w.title())
                w = w.parentWidget()
            value, origin = self._current(c.path)
            out.append(dict(path=c.path, tab=tab, groups=groups, label=c.lbl.text(), value=value, origin=origin,
                            xml=self.s.xml_path_of(c.path), active=c.isEnabled()))
        return out

    # -- changes since the last load / save ----------------------------------------------------
    def _tracked_paths(self) -> list[str]:
        return [c.path for c in self.controls] + [f"sections.{k}" for k in self.sections] + ["gestaltungen"]

    def _current(self, path: str):
        if path == "gestaltungen":  # which entries exist (added / removed)
            return tuple(sorted((gid, g.typ) for gid, g in self.s.measures.items.items())), "angabe"
        try:
            return self.s.get(path), self.s.origin_of(path)
        except (KeyError, IndexError, AttributeError):
            return None, None

    def mark_saved(self) -> None:
        """Remember the current state as the one in the XML (after loading or saving)."""
        self.baseline = {p: copy.deepcopy(self._current(p)) for p in self._tracked_paths()}
        self.baseline_items = (copy.deepcopy(self.s.measures.items),
                               {k: v for k, v in self.s.origin.items() if k.startswith("measures.items.")})
        self._update_changes()

    @staticmethod
    def _same(a, b) -> bool:
        if isinstance(a, float) or isinstance(b, float):
            try:
                return abs(float(a) - float(b)) < 1e-6
            except (TypeError, ValueError):
                return False
        return a == b

    def changes(self) -> list[tuple]:
        """[(path, label, tab, saved value, current value, saved origin, current origin)]"""
        out = []
        labels = {c.path: c.lbl.text() for c in self.controls}
        for p in self._tracked_paths():
            if p not in self.baseline:  # appeared later (e.g. new horizon year): start tracking now
                self.baseline[p] = copy.deepcopy(self._current(p))
                continue
            (v0, o0), (v1, o1) = self.baseline[p], self._current(p)
            if self._value_changed(p, v0, v1, o1) or o0 != o1:
                tab = next((t for t, ps in zip(self.tab_titles, self.tab_paths) if p in ps), "")
                lab = labels.get(p) or ("Gestaltungen hinzugefügt/entfernt" if p == "gestaltungen" else
                                        f"Bereich „{self.sections[p.split('.')[1]][0].text()}“")
                out.append((p, lab, tab, v0, v1, o0, o1))
        return out

    def _value_changed(self, path: str, v0, v1, origin: str) -> bool:
        """A value the program derives (origin "abgeleitet", or the years of an automatic horizon) follows the other
        inputs and is not a change of its own."""
        if path in ("options.horizon_start", "options.horizon_end") and self.s.options.horizon_auto:
            return False
        return not self._same(v0, v1) and not (origin == "abgeleitet" and is_program_derived(path))

    def has_changes(self) -> bool:
        return bool(self.changes())

    def _update_changes(self) -> None:
        if not hasattr(self, "baseline"):
            return
        changed = {c[0]: c for c in self.changes()}
        for c in self.controls:
            ch = changed.get(c.path)
            vtip = otip = ""
            if ch:
                _, _, _, v0, v1, o0, o1 = ch
                if self._value_changed(c.path, v0, v1, o1):
                    vtip = f"<b>Wert geändert</b> seit dem letzten Laden/Speichern<br/>gespeichert: {escape(fmt_path_value(c.path, v0))}"
                if o0 != o1:
                    otip = (f"<b>Herkunft geändert</b> seit dem letzten Laden/Speichern<br/>gespeichert: "
                            f"{escape(HERKUNFT_LABEL.get(o0, str(o0)))}")
            c.set_changed(vtip, otip)
        dot = _red_dot_icon()
        for i, (title, paths) in enumerate(zip(self.tab_titles, self.tab_paths)):
            self.tabs.setTabText(i, title.replace("&", "&&"))
            self.tabs.setTabIcon(i, dot if paths & changed.keys() else QIcon())
            self.tabs.setTabToolTip(i, "Enthält Änderungen seit dem letzten Laden/Speichern" if paths & changed.keys() else "")

    def reset_value(self, path: str, what: str = "both") -> None:
        """Back to the value and/or origin of the last loaded / saved state."""
        if path not in getattr(self, "baseline", {}):
            return
        v0, o0 = self.baseline[path]
        if path == "gestaltungen":  # all entries back to the saved state
            items, origins = copy.deepcopy(self.baseline_items)
            self.s.measures.items = items
            for k in [k for k in self.s.origin if k.startswith("measures.items.")]:
                del self.s.origin[k]
            self.s.origin.update(origins)
            self.rebuild()
            self.settingsChanged.emit()
            return
        if path == "familienstand":
            set_familienstand(self.s, v0)
            self.rebuild()
            self.settingsChanged.emit()
            return
        if what in ("value", "both"):
            self.s.set(path, copy.deepcopy(v0))
        if what in ("origin", "both") and o0 is not None:
            self.s.origin[path] = o0
        self.refresh()
        self.settingsChanged.emit()

    def _show_section(self, key: str) -> None:
        check, content, box = self.sections[key]
        on = self.s.active(key)
        check.blockSignals(True)
        check.setChecked(on)
        check.blockSignals(False)
        content.setEnabled(on)
        for i in range(self.tabs.count()):
            sa = self.tabs.widget(i)
            if isinstance(sa, QScrollArea) and sa.widget() is box:
                self.tabs.tabBar().setTabTextColor(i, self.palette().color(
                    self.palette().ColorGroup.Disabled if not on else self.palette().ColorGroup.Active,
                    self.palette().ColorRole.WindowText))

    RISK_COLORS = {"keins": ("#a6dcb0", "#0d3a16"), "gering": ("#cfe8c9", "#1e4a14"),
                   "gering, wenn echt": ("#cfe8c9", "#1e4a14"), "gering bis mittel": ("#f6e3a6", "#4a3a00"),
                   "mittel": ("#f6c26b", "#4a2a00")}

    def _risk(self, lay, level: str, text: str, rules: list[str]) -> None:
        """Ä10: one-line risk badge with tooltip (R_Gestaltungsrisiko and the rule of the measure)."""
        bg, fg = self.RISK_COLORS.get(level, ("#d6d6d6", "#333333"))
        lab = QLabel(f"<span style='background:{bg}; color:{fg}'>&nbsp;Gestaltungsrisiko: {escape(level)}&nbsp;</span> ⓘ")
        lab.setToolTip(self._tt(["R_Gestaltungsrisiko"] + rules, text=text))
        lay.addWidget(lab)

    @staticmethod
    def _hint(text: str) -> QLabel:
        lab = QLabel(f"<small><i>{escape(text)}</i></small>")
        lab.setWordWrap(True)
        lab.setIndent(12)
        return lab

    def _subheading(self, lay, text: str) -> None:
        lab = QLabel(f"<b>{escape(text)}</b>")
        lab.setContentsMargins(0, 6, 0, 0)
        lay.addWidget(lab)

    def _salary_years(self, i: int) -> list[int]:
        o = self.s.options
        ps = self.s.persons[i]
        return sorted(set(self._years()) | {y for y in ps.salary if y >= o.horizon_start - 1})

    def _set_salary_mode(self, i: int, mode: str) -> None:
        set_salary_mode(self.s, i, mode, [y for y, _, _ in self.salary_rows.get(i, [])])
        self.refresh()
        self.settingsChanged.emit()

    def _update_salary_info(self) -> None:
        """Read-only prorated wage below each year; years after the exit are greyed out."""
        for i, rows in self.salary_rows.items():
            ps = self.s.persons[i]
            for y, ctrl, info in rows:
                em = ps.employed_months(y)
                ctrl.setEnabled(em > 0)
                info.setEnabled(em > 0)
                months = f"{em:.2f}".replace(".", ",").rstrip("0").rstrip(",")
                info.setToolTip("")
                if not ps.austritt:
                    info.setText("")  # no exit: the whole year counts, nothing to prorate
                elif em <= 0:
                    info.setText(f"<small>nach dem Austritt am {ps.end_date:%d.%m.%Y} – nicht relevant</small>")
                elif ps.salary_mode == "jahr":
                    info.setText(f"<small>anteilig bis Austritt ({months} Monate): <b>{fmt_eur(ps.prorated(y))}</b></small>")
                else:
                    info.setText(f"<small>hochgerechnet auf ein ganzes Jahr ({months} Monate gearbeitet): "
                                 f"<b>{fmt_eur(ps.annual_equiv(y))}</b> ⓘ</small>")
                    info.setToolTip(ANNUAL_EQUIV_TIP)
                info.setVisible(bool(info.text()))

    def _scroll(self, w: QWidget) -> QScrollArea:
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        sa.setWidget(w)
        return sa

    def _sub_box(self, parent_lay, depends: str) -> QVBoxLayout:
        """Part of a group that is greyed out together (``depends`` = path of the switch)."""
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        parent_lay.addWidget(w)
        self.dependent.append((w, depends))
        return v

    def _group(self, parent_lay, title: str) -> QVBoxLayout:
        g = QGroupBox(title)
        v = QVBoxLayout(g)
        v.setSpacing(4)
        parent_lay.addWidget(g)
        return v

    def _add(self, lay, ctrl: Bound, depends: str | None = None) -> Bound:
        """Add a bound control; ``depends`` = path of a switch that enables it ('!path' = enabled when off)."""
        ctrl.changed.connect(self._on_changed)
        ctrl.originClicked.connect(self._choose_origin)
        ctrl.resetRequested.connect(self.reset_value)
        self.controls.append(ctrl)
        lay.addWidget(ctrl)
        if depends:
            self.dependent.append((ctrl, depends))
        return ctrl

    def _update_dependent(self) -> None:
        for ctrl, dep in self.dependent:
            neg = dep.startswith("!")
            on = bool(self.s.get(dep.lstrip("!")))
            ctrl.setEnabled(on != neg)

    def _tt(self, rules=(), params=(), text=""):
        return refs_tooltip(self.legal, rules, params, text)

    def _years(self):
        return self.s.years()

    def _person_tab(self, i: int) -> QWidget:
        s, ps = self.s, self.s.persons[i]
        b = f"persons.{i}"
        w = QWidget()
        lay = QVBoxLayout(w)
        o = s.options
        lo_m, hi_m = month_index(o.horizon_start, 1), month_index(o.horizon_end, 12)
        d_lo, d_hi = date(o.horizon_start - 1, 1, 1), date(o.horizon_end + 1, 12, 31)

        g = self._group(lay, "Person")
        if i == 0:
            self._add(g, ChoiceEdit("familienstand", "Familienstand", FAMILIENSTAND))
            g.addWidget(self._hint("Nur bei „verheiratet“ gibt es den Tab „Ehepartner“; er geht dann immer in Berechnung "
                                   "und Optimierung ein (Zusammen- oder Einzelveranlagung je Jahr im Tab „Haushalt“). Bei "
                                   "einem anderen Familienstand ist der Tab ausgeblendet; vorhandene Daten des Ehepartners "
                                   "bleiben in der Datei erhalten."))
        else:
            fam = ChoiceEdit("familienstand", "Familienstand", FAMILIENSTAND)  # display only, not a separate value
            fam.set_value(s.familienstand)
            fam.set_origin("abgeleitet")
            fam.set_derived(True, "Abgeleitet aus dem Familienstand der/des Steuerpflichtigen.")
            g.addWidget(fam)
            g.addWidget(self._hint("Abgeleitet aus dem Familienstand im Tab „Steuerpflichtige(r)“ und nur dort änderbar. "
                                   "Den Tab „Ehepartner“ gibt es nur bei „verheiratet“."))
        self._add(g, DateEdit(f"{b}.birth", "Geburtsdatum", date(1940, 1, 1), date(s.stand.year - 14, 12, 31), slider=False,
                              tooltip=self._tt(["R_ALG_Dauer", "R_Ruhen158"], ["alg_ruhen158_anrechnung_alter_ab"],
                                               "Das Alter bestimmt die ALG-Anspruchsdauer und den anrechenbaren Anteil "
                                               "der Abfindung beim Ruhen nach § 158 SGB III.")))
        self._add(g, ChoiceEdit(f"{b}.steuerklasse", "Steuerklasse", [(k, k) for k in ("I", "II", "III", "IV", "V", "VI")],
                                tooltip=self._tt(["R_LSt_Abfindung", "R_ALG_Hoehe"], text="Wirkt auf den Lohnsteuerabzug "
                                                 "(Liquiditätsplan) und den abgeleiteten ALG-Betrag, nicht auf die "
                                                 "Einkommensteuer.")))

        g = self._group(lay, "Bisherige Beschäftigung")
        leaves = f"{b}.austritt"
        self._add(g, BoolEdit(leaves, "Scheidet aus (Austritt mit Abfindung)",
                              tooltip=self._tt([], text="Aus: Die Beschäftigung läuft im ganzen Horizont weiter (Gehalt, "
                                               "Arbeitnehmeranteile KV/PV). Abfindung, ALG, Sperrzeit und neue "
                                               "Beschäftigung entfallen; die Werte bleiben gespeichert.")))
        outer = g
        g = self._sub_box(outer, leaves)
        self._subheading(g, "Austritt")
        self._add(g, DateEdit(f"{b}.end_date", "Austrittsdatum (Ende Arbeitsverhältnis)", d_lo, d_hi,
                              tooltip=self._tt(["R_Ruhen158", "R_Sperrzeit", "R_LaufenderArbeitslohn"])))
        self._add(g, DateEdit(f"{b}.vertragsschluss", "Datum Kündigung / Aufhebungsvertrag (für Fristberechnung)", d_lo,
                              d_hi, slider=False, tooltip=self._tt(["R_Ruhen158"], ["alg_ruhen158_max_jahre"])))
        self._add(g, NumberEdit(f"{b}.kfrist_monate", "Kündigungsfrist des Arbeitgebers (Monate)", 0, 12, 1, 0, " Mon.",
                                slider=False, integer=False,
                                tooltip=self._tt(["R_Ruhen158"], text="Herkunft „abgeleitet“: gesetzliche Frist aus der "
                                                 "Tabelle T_Kuendigungsfristen_AG nach der Betriebszugehörigkeit.")))
        self._add(g, NumberEdit(f"{b}.bz_jahre", "Betriebszugehörigkeit (Jahre)", 0, 45, 1, 0, " J.", slider=False,
                                tooltip=self._tt(["R_Ruhen158", "R_ALG_Dauer"], ["alg_ruhen158_anrechnung_schritt"],
                                                 "Auch ohne Fristtabelle relevant: mindert den anrechenbaren Anteil der "
                                                 "Abfindung beim Ruhen nach § 158 und bestimmt die versicherten Monate "
                                                 "für Anwartschaft und Anspruchsdauer.")))
        g = outer
        self._subheading(g, "Gehalt")
        mode = ChoiceEdit(f"{b}.salary_mode", "Eingabe des Bruttogehalts",
                          [("jahr", "Gehalt bei Beschäftigung über das ganze Jahr"),
                           ("real", "Tatsächlich gezahltes Gehalt im jeweiligen Jahr")],
                          tooltip=self._tt(["R_LaufenderArbeitslohn"], text="Bei „ganzes Jahr“ wird das anteilige Gehalt "
                                           "bis zum Austrittsdatum berechnet. Gehalt einer neuen Stelle unter „Neue Beschäftigung“."))
        mode.changed.connect(lambda _p, v, i=i: self._set_salary_mode(i, v))
        self.controls.append(mode)
        g.addWidget(mode)
        rows = []
        for y in self._salary_years(i):
            val = ps.salary_for(y)[0]
            ctrl = self._add(g, NumberEdit(f"{b}.salary.{y}", f"Bruttogehalt {y}", 0, max(250_000, 2 * val), 500,
                                           tooltip=self._tt(["R_LaufenderArbeitslohn"],
                                                            text="Fehlt ein Jahr, wird das Vorjahr fortgeschrieben. "
                                                            "Das Gehalt eines Jahres ohne Abfindung beeinflusst die Steuer "
                                                            "auf Abfindungen anderer Jahre nicht. Es ist aber relevant für "
                                                            "Zahlungsjahre, Veranlagungsart, Meldung nach mehr als einem "
                                                            "Jahr, KV und Basisrenten-Höchstbetrag.")))
            info = QLabel()
            info.setIndent(12)
            g.addWidget(info)
            rows.append((y, ctrl, info))
        self.salary_rows[i] = rows
        g = self._sub_box(outer, leaves)
        self._subheading(g, "Abfindung")
        self._add(g, NumberEdit(f"{b}.severance", "Höhe der Abfindung (brutto)", 0, max(600_000, 2 * ps.severance), 1000,
                                tooltip=self._tt(["R_Entschaedigung", "R_Ruhen158"])))
        self._add(g, BoolEdit(f"{b}.fenster_aktiv", "Auszahlungsfenster laut Abfindungsangebot",
                              tooltip=self._tt(["R_Faelligkeit"], ["abf_auszahlung_spaetestens_monate_default"],
                                               "Frühester Termin ist die Entgeltabrechnung des Austrittsmonats. Der Zahlungstermin "
                                               "muss vor Fälligkeit vereinbart sein. Der Optimierer durchsucht alle Jahre im Fenster.")))
        dep = f"{b}.fenster_aktiv"
        self._add(g, MonthEdit(f"{b}.fenster_ab_idx", "frühestens", lo_m, hi_m), depends=dep)
        self._add(g, IntEdit(f"{b}.fenster_monate", "spätestens (Monate nach Austritt)", 1, 120, " Mon."), depends=dep)
        self._risk(g, "gering bis mittel", "Späterer Zahlungstermin: nur anerkannt, wenn vor Fälligkeit vereinbart und so "
                   "umgesetzt; bereits fällige Beträge dürfen nicht verschoben werden.", ["R_Faelligkeit"])
        self._add(g, MonthEdit(f"{b}.pay_idx", "Zahlungsmonat der Abfindung", lo_m, hi_m,
                               tooltip=self._tt(["R_Zufluss", "R_Fuenftel_Progressionsvorbehalt"])))
        self._add(g, BoolEdit(f"{b}.fuenftel_ok", "Voraussetzungen der Fünftelregelung erfüllt",
                              tooltip=self._tt(["R_Entschaedigung", "R_Zusammenballung"])))

        g = self._group(lay, "Arbeitslosengeld")
        self.dependent.append((g.parentWidget(), leaves))
        claims = f"{b}.alg_aktiv"
        self._add(g, BoolEdit(claims, "Arbeitslosengeld beantragen",
                              tooltip=self._tt(["R_ALG_Dauer", "R_KV_ALG"], text="Aus: keine Meldung bei der Agentur für "
                                               "Arbeit, kein ALG, keine Sperrzeit. Nach dem Austritt richtet sich die KV "
                                               "nach dem nachgehenden Anspruch, der Familienversicherung oder der "
                                               "freiwilligen Versicherung.")))
        g = self._sub_box(g, claims)
        opts = [(0, "keine Sperrzeit (wichtiger Grund)")]
        for pid in ("alg_sperrzeit_arbeitsaufgabe_kurz_wochen", "alg_sperrzeit_arbeitsaufgabe_haerte_wochen",
                    "alg_sperrzeit_arbeitsaufgabe_wochen"):
            if self.legal.has(pid):
                wk = int(self.legal.value(pid))
                opts.append((wk, f"{wk} Wochen ({pid})"))
        self._add(g, ChoiceEdit(f"{b}.sperrzeit_wochen", "Sperrzeit", opts,
                                tooltip=self._tt(["R_Sperrzeit", "R_WichtigerGrund", "R_ALG_Dauer"])))
        self._add(g, DateEdit(f"{b}.meldung", "Arbeitslosmeldung (Antrag ALG)", date(o.horizon_start, 1, 1),
                              date(o.horizon_end + 1, 12, 31),
                              tooltip=self._tt(["R_ALG_Dauer", "R_Parallel"], ["alg_minderung_entfaellt_nach_jahren"])))
        self._add(g, DateEdit(f"{b}.arbeitsuchend_datum", "Arbeitsuchendmeldung", d_lo, d_hi, slider=False,
                              tooltip=self._tt(["R_Sperrzeit"], ["alg_arbeitsuchend_frist_monate"])))
        self._add(g, NumberEdit(f"{b}.alg_monat", "ALG-Monatsbetrag", 0, 4000, 10,
                                tooltip=self._tt(["R_ALG_Hoehe"], ["alg_tage_pro_monat"],
                                                 "Herkunft „abgeleitet“: eigene Berechnung aus dem Bemessungsentgelt "
                                                 "(§§ 149 ff. SGB III).")))
        self._add(g, IntEdit(f"{b}.vorbeschaeftigung_monate", "Versicherte Monate vor dem jetzigen Arbeitgeber", 0, 240,
                             " Mon.", tooltip=self._tt(["R_ALG_Dauer"], ["alg_anwartschaft_monate"])))

        g = self._group(lay, "Neue Beschäftigung")
        self.dependent.append((g.parentWidget(), leaves))
        self._add(g, BoolEdit(f"{b}.newjob", "Neue Beschäftigung aufnehmen"))
        self._add(g, DateEdit(f"{b}.newjob_start", "Beginn", date(o.horizon_start, 1, 1), date(o.horizon_end + 1, 12, 31)))
        self._add(g, NumberEdit(f"{b}.newjob_salary", "Jahresgehalt (brutto)", 0, 250_000, 1000))

        g = self._group(lay, "Krankenversicherung")
        insured = f"{b}.kv_aktiv"
        self._add(g, BoolEdit(insured, "Krankenversicherung berücksichtigen",
                              tooltip=self._tt(["R_KV_ALG", "R_KV_Freiwillig"], text="Aus: Für diese Person werden keine "
                                               "KV/PV-Beiträge gerechnet (auch keine Arbeitnehmeranteile) und keine "
                                               "KV/PV-Vorsorgeaufwendungen abgezogen, z. B. wenn die Versicherung "
                                               "außerhalb des Programms betrachtet wird.")))
        g = self._sub_box(g, insured)
        self._add(g, ChoiceEdit(f"{b}.kv_status", "KV-Status vor dem Austritt",
                                [("pflichtversichert", "pflichtversichert"), ("freiwillig_gesetzlich", "freiwillig gesetzlich"),
                                 ("privat", "privat"), ("unbekannt", "unbekannt")],
                                tooltip=self._tt(["R_KV_ALG", "R_KV_RuhenAbfindung", "R_KV_Familie"])))
        self._add(g, NumberEdit(f"{b}.kv_beitrag_schaetzung", "Freiwilliger/privater Beitrag je Monat", 0,
                                2000, 5, tooltip=self._tt(["R_KV_Freiwillig"], text="Herkunft „abgeleitet“: aus den "
                                                          "Einnahmen nach den Regeln der freiwilligen Versicherung berechnet.")))
        self._add(g, NumberEdit(f"{b}.kv_sonstige_einnahmen", "Sonstige beitragspflichtige Einnahmen je Monat", 0, 10_000, 50,
                                tooltip=self._tt(["R_KV_Freiwillig"], ["kv_mindestbemessung_monat", "kv_bbg_monat"])))

        g = self._group(lay, "Steuer und weitere Einkünfte")
        self._add(g, NumberEdit(f"{b}.werbungskosten", "Werbungskosten je Jahr", 0, 20_000, 50,
                                tooltip=self._tt([], ["est_arbeitnehmer_pauschbetrag"])))
        if ps.rent:
            y = max(ps.rent)
            self._add(g, NumberEdit(f"{b}.rent.{y}", f"Einkünfte Vermietung (Basis {y}, fortgeschrieben)", -50_000, 100_000, 100,
                                    tooltip=self._tt(["R_Verlustausgleich"])))
        if ps.capital:
            y = max(ps.capital)
            self._add(g, NumberEdit(f"{b}.capital.{y}", f"Kapitalerträge (Basis {y}, fortgeschrieben)", 0, 200_000, 100,
                                    tooltip=self._tt(["R_Abgeltung", "R_KV_Freiwillig"])))
        self._add(g, BoolEdit(f"{b}.rv_pflichtig", "Rentenversicherungspflichtig", tooltip=self._tt(["R_Basisrente"])))
        lay.addStretch(1)
        return w

    def _household_tab(self) -> QWidget:
        s = self.s
        w = QWidget()
        lay = QVBoxLayout(w)
        g = self._group(lay, "Haushalt")
        g.addWidget(QLabel(f"Veranlagung: {'Zusammenveranlagung (Splitting)' if s.joint else 'Einzelveranlagung'}"))
        self._add(g, ChildrenEdit("children", "Kinder (Geburtsjahr, Kindergeldbezug)", s.stand.year - 30, s.stand.year + 5,
                                  tooltip=self._tt(["R_Guenstigerpruefung", "R_ALG_Hoehe"],
                                                   ["alg_satz_mit_kind", "alg_satz_ohne_kind"],
                                                   "Das Geburtsjahr bestimmt, in welchen Jahren Kinderfreibeträge, "
                                                   "PV-Abschläge und Betreuungskosten zählen; der Kindergeldbezug den "
                                                   "höheren ALG-Leistungssatz und die Günstigerprüfung.")))
        self._add(g, BoolEdit("options.church", "Kirchensteuerpflichtig",
                              tooltip=self._tt([], ["kist_satz_by_bw", "kist_satz_sonst"])))
        self._add(g, ChoiceEdit("options.bundesland", "Bundesland", [(b, b) for b in BUNDESLAENDER]))
        self._add(g, BoolEdit("objekte_angeschafft_3j", "Mietobjekte in den letzten 3 Jahren angeschafft",
                              tooltip=self._tt(["R_Erhaltung"], text="Dann kann Erhaltungsaufwand als anschaffungsnahe "
                                               "Herstellungskosten gelten (§ 6 Abs. 1 Nr. 1a EStG): Warnung im Ergebnis.")))
        for y in sorted(s.childcare):
            self._add(g, NumberEdit(f"childcare.{y}", f"Kinderbetreuungskosten (Basis {y}, fortgeschrieben)", 0, 30_000, 100,
                                    tooltip=self._tt([], ["kind_betreuung_anteil", "kind_betreuung_hoechstbetrag"])))
        if s.married and len(s.persons) >= 2:
            g = self._group(lay, "Veranlagung je Jahr")
            self._risk(g, "keins", "Einzelveranlagung: gesetzliches Wahlrecht (§§ 26, 26a EStG).", ["R_Einzelveranlagung"])
            tt = self._tt(["R_Einzelveranlagung"], text="Die Wahl wird erst mit der Steuererklärung getroffen. "
                          "„Automatisch“ rechnet beide Arten und nimmt die günstigere.")
            opts = [("auto", "automatisch (günstigere)"), ("zusammen", "Zusammenveranlagung"), ("einzel", "Einzelveranlagung")]
            for y in self._years():
                if y not in s.veranlagung:
                    s.veranlagung[y] = "auto" if s.joint else "einzel"
                self._add(g, ChoiceEdit(f"veranlagung.{y}", f"Veranlagung {y}", opts, tooltip=tt))
            self._add(g, BoolEdit("sa_haelftig", "Bei Einzelveranlagung Sonderausgaben je zur Hälfte (§ 26a Abs. 2 EStG)",
                                  tooltip=self._tt(["R_Einzelveranlagung"], ["est_einzelveranlagung_sonderausgaben_haelftig"])))
        g = self._group(lay, "Steuer")
        self._add(g, NumberEdit("options.tarif_index", "Fortschreibung des Tarifs für Jahre ohne eigenen Tarif (p. a.)",
                                0, 0.05, 0.0025, 2, " %", 100, tooltip=self._tt([], [], "0 % = Tarif unverändert fortgeschrieben.")))
        self._add(g, ChoiceEdit("options.guenstiger_mode", "Günstigerprüfung Kinder",
                                [("voll", "mit § 34 und § 32b (vollständige Berechnung)"), ("tarif", "nur auf Tarifbasis")],
                                tooltip=self._tt(["R_Guenstigerpruefung"])))
        self._add(g, NumberEdit("options.sozialabgaben_anteil", "Sozialabgaben-Anteil am Gehalt (Netto, Vorsorgepauschale)",
                                0, 0.3, 0.005, 1, " %", 100))
        if not self.legal.pick("rv_beitragssatz_gesamt", "rv_beitragssatz"):
            self._add(g, NumberEdit("options.rv_satz_annahme", "RV-Beitragssatz (fehlt in rechtlicher XML!)", 0, 0.25,
                                    0.001, 1, " %", 100, tooltip=self._tt(["R_Basisrente"], [],
                                                                         "Bitte Parameter rv_beitragssatz_gesamt in die rechtlichen Vorgaben aufnehmen.")))
        self._add(g, IntEdit("options.bescheid_monat", "Monat des Steuerbescheids im Folgejahr (Liquidität)", 1, 12,
                             tooltip=self._tt(["R_LSt_Abfindung"])))
        lay.addStretch(1)
        return w

    def _kv_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        g = self._group(lay, "Beiträge freiwillig Versicherter")
        self._add(g, NumberEdit("options.kv_zusatz", "Zusatzbeitrag", 0, 0.05, 0.0005, 2, " %", 100,
                                tooltip=self._tt(["R_KV_Freiwillig"], ["kv_zusatzbeitrag_durchschnitt"])))
        self._add(g, BoolEdit("options.kv_satz_allgemein", "Allgemeiner statt ermäßigter Beitragssatz",
                              tooltip=self._tt([], ["kv_satz_allgemein", "kv_satz_ermaessigt"])))
        self._add(g, ChoiceEdit("options.kv_abfindung_mode", "Abfindung bei freiwilliger Versicherung",
                                [(1, "1 – nicht verbeitragt"), (2, "2 – dem Fristzeitraum zugeordnet"),
                                 (3, "3 – auf 12 Monate ab Zufluss verteilt")],
                                tooltip=self._tt(["R_KV_Freiwillig", "R_KV_AbfindungPflicht"], ["kv_abfindung_verteilung_monate"])))
        g = self._group(lay, "Offene Rechtsfrage")
        self._add(g, BoolEdit("options.kv_nachgehend_vorrang",
                              "Nachgehender Leistungsanspruch hat Vorrang vor der Anschlussversicherung (1. Monat beitragsfrei)",
                              tooltip=self._tt(["R_KV_RuhenAbfindung"], ["kv_nachgehender_anspruch_monate"])))
        lay.addStretch(1)
        return w

    GEGENWERT_HELP = {
        "basisrente": "100 % = gebundenes Vermögen ohne Wertverlust; weniger, wenn die Bindung bis zur Rente oder die "
                      "spätere Besteuerung als Nachteil gewertet wird.",
        "erhaltung": "100 % = Maßnahme ist ohnehin nötig und wird nur vorgezogen; weniger, wenn sie ohne den "
                     "Steuereffekt (noch) nicht gemacht würde.",
        "spende": "0 % = das Geld ist weg; mehr, wenn der Zweck für dich einen Wert hat.",
        "kauf": "Bezogen auf die laufenden Netto-Kosten (Zinsen + Bewirtschaftung + Disagio − Miete). Kaufpreis, "
                "Eigenkapital und Tilgung sind ohnehin Umschichtung.",
        "sonstige": "Anteil des Betrags, der als Vermögen oder persönlicher Wert erhalten bleibt.",
    }

    def _gegenwert(self, gid: str, typ: str) -> NumberEdit:
        return NumberEdit(f"measures.items.{gid}.gegenwert", "Gegenwert (Anteil, der nicht als Aufwand in den Saldo "
                          "eingeht)", 0, 1, 0.05, 0, " %", 100,
                          tooltip=self._tt([], text="Im Saldo zählt nur (1 − Gegenwert) × Betrag als Aufwand; die "
                                           "Steuerwirkung zählt immer voll. " + self.GEGENWERT_HELP[typ]))

    def _measures_tab(self) -> QWidget:
        s = self.s
        o = s.options
        w = QWidget()
        lay = QVBoxLayout(w)
        g = self._group(lay, "Neue Gestaltung")  # two rows, so the tab stays as narrow as the others
        self.add_typ = compact_combo(QComboBox())
        for key, (lab, _, _) in GESTALTUNG_TYPEN.items():
            self.add_typ.addItem(lab, key)
        g.addWidget(self.add_typ)
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(QLabel("Jahr"))
        self.add_year = QSpinBox()
        self.add_year.setRange(o.horizon_start - 1, o.horizon_end + 5)
        pay_years = sorted({ps.pay_year for ps in s.persons})
        self.add_year.setValue(min(max(pay_years[-1] if pay_years else o.horizon_start, o.horizon_start), o.horizon_end))
        h.addWidget(self.add_year)
        h.addStretch(1)
        btn = QPushButton("Hinzufügen")
        btn.clicked.connect(lambda: self.add_gestaltung(self.add_typ.currentData(), self.add_year.value()))
        h.addWidget(btn)
        g.addWidget(row)
        lay.addWidget(self._hint("Jede Art kann mehrfach und in verschiedenen Jahren angelegt werden. Der Optimierer kann "
                                 "je Jahr eine Basisrente bis zur Nullgrenze vorschlagen; Einträge mit Herkunft ≠ "
                                 "„Planung“ bleiben dabei fest."))
        self.br_info = {}
        self.item_boxes = {}
        items = gestaltungen(s)
        if not items:
            lay.addWidget(QLabel("<i>Noch keine Gestaltungen angelegt.</i>"))
        for gid, g in items:
            self._gestaltung_box(lay, gid, g)
        lay.addStretch(1)
        return w

    def _gestaltung_box(self, lay, gid: str, g) -> None:
        o = self.s.options
        b = f"measures.items.{gid}"
        box = QGroupBox(g.label)
        v = QVBoxLayout(box)
        v.setSpacing(4)
        lay.addWidget(box)
        self.item_boxes[gid] = box
        top = QHBoxLayout()
        risks = {"basisrente": ("gering", "Basisrente: gesetzlich vorgesehen; zertifizierter Vertrag; tatsächlicher Abfluss "
                                "im Jahr.", ["R_Basisrente"]),
                 "erhaltung": ("gering, wenn echt", "Erhaltungsaufwand: keine Vorauszahlung ohne Leistung; Abgrenzung zu "
                               "Herstellungskosten.", ["R_Erhaltung"]),
                 "kauf": ("mittel", "Immobilienkauf mit Verlusten: Einkünfteerzielungsabsicht, § 15b EStG, Vermietung an "
                          "Angehörige, Rückverkauf. Disagio (gering bis mittel): über der Marktüblichkeit nicht sofort "
                          "abziehbar.", ["R_Erhaltung", "R_Grenzen_Gestaltung"])}
        if g.typ in risks:
            tmp = QVBoxLayout()
            self._risk(tmp, *risks[g.typ])
            top.addLayout(tmp)
        top.addStretch(1)
        rm = QPushButton("Entfernen")
        rm.setToolTip("Diese Gestaltung entfernen (Rückgängig über die Werkzeugleiste)")
        rm.clicked.connect(lambda _=False, gid=gid: self.remove_gestaltung(gid))
        top.addWidget(rm)
        v.addLayout(top)
        y_lo, y_hi = min(o.horizon_start - 1, g.jahr), max(o.horizon_end + 5, g.jahr)
        if g.typ == "kauf":
            self._add(v, IntEdit(f"{b}.jahr", "Jahr Besitzübergang", y_lo, y_hi))
            self._add(v, IntEdit(f"{b}.monat", "Monat Besitzübergang", 1, 12))
            self._add(v, NumberEdit(f"{b}.kaufpreis", "Kaufpreis", 0, 2_000_000, 5000))
            self._add(v, NumberEdit(f"{b}.gebaeudeanteil", "Gebäudeanteil", 0, 1, 0.01, 0, " %", 100))
            self._add(v, NumberEdit(f"{b}.nebenkosten_anteil", "Erwerbsnebenkosten (Anteil am Kaufpreis)", 0, 0.2, 0.005, 1,
                                    " %", 100))
            self._add(v, ChoiceEdit(f"{b}.afa_art", "AfA-Art", [("standard", "linear (1925–2022)"), ("ab2023", "linear (ab 2023)"),
                                                               ("vor1925", "linear (vor 1925)"), ("degressiv", "degressiv")],
                                    tooltip=self._tt([], ["verm_afa_satz_standard", "verm_afa_satz_ab2023",
                                                          "verm_afa_satz_vor1925", "verm_afa_degressiv_satz"])))
            self._add(v, NumberEdit(f"{b}.darlehen", "Darlehen", 0, 2_000_000, 5000))
            self._add(v, NumberEdit(f"{b}.zins", "Zinssatz", 0, 0.1, 0.0005, 2, " %", 100))
            self._add(v, NumberEdit(f"{b}.disagio_anteil", "Disagio", 0, 0.1, 0.005, 1, " %", 100,
                                    tooltip=self._tt([], ["verm_disagio_max_anteil", "verm_disagio_min_zinsbindung_jahre"])))
            self._add(v, IntEdit(f"{b}.zinsbindung_jahre", "Zinsbindung (Jahre)", 1, 30))
            self._add(v, NumberEdit(f"{b}.miete_jahr", "Kaltmiete je Jahr", 0, 100_000, 100))
            self._add(v, NumberEdit(f"{b}.ortsuebliche_miete_jahr", "Ortsübliche Miete je Jahr", 0, 100_000, 100,
                                    tooltip=self._tt([], ["verm_verbilligt_untergrenze", "verm_verbilligt_prognosegrenze"])))
            self._add(v, NumberEdit(f"{b}.bewirtschaftung_jahr", "Bewirtschaftungskosten je Jahr", 0, 30_000, 100))
            self._add(v, NumberEdit(f"{b}.kauf_erhaltung", "Instandsetzung nach Kauf", 0, 300_000, 1000,
                                    tooltip=self._tt([], ["verm_anschaffungsnah_grenze", "verm_anschaffungsnah_jahre"])))
        else:
            if g.typ == "sonstige":
                self._add(v, TextEdit(f"{b}.name", "Bezeichnung", placeholder="z. B. Fortbildung, Steuerberatung …"))
                persons = self.s.persons[:2 if self.s.married else 1]
                self._add(v, ChoiceEdit(f"{b}.person", "Mindert das Einkommen von", [(ps.id, ps.label) for ps in persons]))
            self._add(v, IntEdit(f"{b}.jahr", "Jahr", y_lo, y_hi))
            tips = {"basisrente": self._tt(["R_Basisrente"], ["av_basisrente_hoechstbetrag_je_person"],
                                           "Bindet Vermögen bis zum Rentenbeginn; die Rente wird später versteuert "
                                           "(Steuerverschiebung). Bis zur Nullgrenze eines Jahres wirkt der Abzug fast "
                                           "vollständig."),
                    "erhaltung": self._tt(["R_Erhaltung"]),
                    "spende": self._tt([], ["est_spenden_hoechstanteil"]),
                    "sonstige": self._tt([], text="Eigene Gestaltung: der abziehbare Anteil mindert das zu versteuernde "
                                         "Einkommen der gewählten Person im Jahr der Zahlung (ohne Höchstbetrag).")}
            labels = {"basisrente": "Einmalbeitrag", "erhaltung": "Betrag", "spende": "Betrag", "sonstige": "Betrag"}
            self._add(v, NumberEdit(f"{b}.betrag", labels[g.typ], 0, 300_000, 100, tooltip=tips[g.typ]))
            if g.typ == "sonstige":
                self._add(v, NumberEdit(f"{b}.abziehbar", "Steuerlich abziehbar (Anteil des Betrags)", 0, 1, 0.05, 0, " %",
                                        100, tooltip=self._tt([], text="Eigene Angabe, welcher Anteil des Betrags vom "
                                                              "Einkommen abgezogen werden darf (Standard 100 %).")))
            self._add(v, IntEdit(f"{b}.monat", "Zahlungsmonat (Liquidität)", 1, 12))
            if g.typ == "basisrente":
                info = QLabel()
                info.setIndent(12)
                v.addWidget(info)
                self.br_info[gid] = info
        self._add(v, self._gegenwert(gid, g.typ))

    def add_gestaltung(self, typ: str, year: int) -> None:
        taken = {p.split(".")[2] for p in getattr(self, "baseline", {}) if p.startswith("measures.items.")}
        add_gestaltung(self.s, typ, year, _taken=taken)
        self.rebuild()
        self.settingsChanged.emit()

    def remove_gestaltung(self, gid: str) -> None:
        remove_gestaltung(self.s, gid)
        self.rebuild()
        self.settingsChanged.emit()

    def _options_tab(self) -> QWidget:
        o = self.s.options
        w = QWidget()
        lay = QVBoxLayout(w)
        g = self._group(lay, "Planungshorizont und Zielgröße")
        self._add(g, BoolEdit("options.horizon_auto", "Horizont automatisch (Austrittsjahr bis spätestes Zahlungsjahr "
                                                      "bzw. Ende des ALG-Bezugs)", tooltip=self._tt(["R_Faelligkeit"])))
        self._add(g, IntEdit("options.horizon_start", "Startjahr", 2000, 2100), depends="!options.horizon_auto")
        self._add(g, IntEdit("options.horizon_end", "Endjahr", 2000, 2100), depends="!options.horizon_auto")
        self._add(g, NumberEdit("options.gegenwert_arbeitszeit", "Gegenwert der Arbeitszeit (Anteil des Nettogehalts, "
                                "der nicht in den Saldo eingeht)", 0, 1, 0.05, 0, " %", 100,
                                tooltip=self._tt([], text="Wert der freien Zeit im Verhältnis zum Nettogehalt. 0 % = das "
                                                 "Nettogehalt zählt voll, freie Zeit hat keinen eigenen Wert; 100 % = freie "
                                                 "Zeit ist so viel wert wie das Gehalt, es zählt nur die Steuerwirkung. "
                                                 "Wichtig, wenn das Austrittsdatum eine Stellschraube ist.")))
        g = self._group(lay, "Lohnsteuer-Freibetrag (ELStAM)")
        g.addWidget(self._hint("Wirkt nur auf die Liquidität: Der Freibetrag mindert den monatlichen Lohnsteuerabzug. Die "
                               "Jahressteuer und der Saldo ändern sich nicht, weil sie mit der Steuererklärung "
                               "abgerechnet werden."))
        self._add(g, NumberEdit("options.lst_freibetrag", "Beantragter Freibetrag", 0, 50_000, 100,
                                tooltip=self._tt(["R_LSt_Ermaessigung"], ["lst_erm_antragsgrenze"])))
        self._add(g, IntEdit("options.lst_freibetrag_year", "Gültigkeitsjahr", o.horizon_start, o.horizon_end))
        self._add(g, DateEdit("options.lst_antrag_datum", "Antragsdatum", date(o.horizon_start - 1, 1, 1),
                              date(o.horizon_end, 12, 31), slider=False,
                              tooltip=self._tt(["R_LSt_Ermaessigung"], ["lst_erm_frist_beginn", "lst_erm_frist_ende"])))
        g = self._group(lay, "Offene Rechtsfragen")
        self._add(g, BoolEdit("options.ein_jahres_regel", "Ein-Jahres-Regel anwenden (Minderung entfällt nach > 1 Jahr)",
                              tooltip=self._tt(["R_ALG_Dauer"], ["alg_minderung_entfaellt_nach_jahren"])))
        lay.addStretch(1)
        return w

    # -- values ----------------------------------------------------------------------
    def refresh(self) -> None:
        for key in self.sections:
            self._show_section(key)
        self._update_salary_info()
        self._update_dependent()
        for c in self.controls:
            try:
                v = self.s.get(c.path)
            except (KeyError, IndexError, AttributeError):
                continue
            if v is None and ".salary." in c.path:
                v = self.s.persons[int(c.path.split(".")[1])].salary_for(int(c.path.rsplit(".", 1)[1]))[0]
            if v is None and c.path.startswith("childcare."):
                v = 0.0
            c.set_value(v)
            c.set_origin(self.s.origin_of(c.path))
        self.wheel_guard.install(self.tabs)  # rows of the children list are created anew
        self._update_changes()

    def set_result(self, res) -> None:
        self._show_derived(res)
        for gid, info in getattr(self, "br_info", {}).items():
            g = self.s.measures.items.get(gid)
            if g is None:
                continue
            y = g.jahr
            ng = sum(t.value for k, t in res.rs.items() if k.startswith("nullgrenze_") and k.endswith(f"_{y}")
                     or k == f"nullgrenze_{y}") if res else 0
            pv = sum(u.pv for (k, yy), u in res.units.items() if yy == y) if res else 0
            info.setText(f"<small>Nullgrenze {y} (zusätzlicher Abzug bis übriges zvE{' + ALG' if pv > 0 else ''} = 0): "
                         f"<b>{fmt_eur(ng)}</b></small>")

    def _show_derived(self, res) -> None:
        """Values with origin "abgeleitet" that the program determines: show the result, lock the inputs."""
        derived = res.ctx.derived if res else {}
        for c in self.controls:
            if c.path in derived and self.s.origin_of(c.path) == "abgeleitet":
                value, tid = derived[c.path]
                obj, last = self.s._resolve(c.path)
                setattr(obj, last, value)  # keep the settings in line (saved with herkunft "abgeleitet")
                c.set_value(value)
                t = res.rs.get(tid)
                steps = "".join(f"<li>{escape(st)}</li>" for st in (t.steps if t else []))
                c.set_derived(True, f"<qt><b>Vom Programm abgeleitet</b> ({escape(t.label) if t else ''})<ol>{steps}</ol>"
                                    "<i>Herkunft auf „Angabe“ oder „Annahme“ stellen, um den Wert selbst festzulegen.</i></qt>")
            elif is_program_derived(c.path):
                c.set_derived(False)
        self._update_changes()

    def _choose_origin(self, path: str, pos) -> None:
        """Menu to set the origin (herkunft) of a value; "Planung" only for values that can be influenced."""
        menu = QMenu(self)
        menu.setToolTipsVisible(True)
        group = QActionGroup(menu)  # exclusive: shown as radio buttons, exactly one origin
        group.setExclusive(True)
        current = self.s.origin_of(path)
        choices = allowed_origins(path)
        for h in choices:
            act = menu.addAction(HERKUNFT_LABEL.get(h, h) + ("  (wird optimiert)" if h == "planung" else ""))
            act.setCheckable(True)
            act.setChecked(h == current)
            act.setData(h)
            act.setToolTip(DERIVED_HELP if (h == "abgeleitet" and is_program_derived(path)) else ORIGIN_HELP.get(h, ""))
            group.addAction(act)
        if len(choices) == 1:
            info = menu.addAction("Einstellung – keine andere Herkunft sinnvoll")
            info.setEnabled(False)
        elif "planung" not in choices:
            info = menu.addAction("„Planung“ nur bei beeinflussbaren Werten")
            info.setEnabled(False)
        chosen = menu.exec(pos)
        if chosen is None or chosen.data() is None or chosen.data() == current:
            return
        self.set_origin(path, chosen.data())

    def set_origin(self, path: str, herkunft: str) -> None:
        paths = [path]
        if any(path.endswith(f) for f in (".fenster_aktiv", ".fenster_ab_idx", ".fenster_monate")):
            base = path.rsplit(".", 1)[0]  # one XML element: Auszahlungsfenster
            paths = [f"{base}.{f}" for f in ("fenster_aktiv", "fenster_ab_idx", "fenster_monate")]
        for p in paths:
            self.s.set_origin(p, herkunft)
        for c in self.controls:
            if c.path in paths:
                c.set_origin(herkunft)
        self._update_changes()
        self.settingsChanged.emit()

    def _on_changed(self, path: str, value) -> None:
        if path == "familienstand":
            set_familienstand(self.s, value)
            self.rebuild()
            self.settingsChanged.emit()
            return
        self.s.set(path, value)
        if path.startswith("measures.items.") and path.rsplit(".", 1)[1] in ("jahr", "name"):
            gid = path.split(".")[2]
            if gid in getattr(self, "item_boxes", {}):
                self.item_boxes[gid].setTitle(self.s.measures.items[gid].label)
        if path == "children":
            self.wheel_guard.install(self.tabs)
        if path in ("options.horizon_start", "options.horizon_end"):
            o = self.s.options
            if o.horizon_end < o.horizon_start:
                o.horizon_end = o.horizon_start
            self.rebuild()
        self._update_salary_info()
        self._update_dependent()
        self._update_changes()
        self.settingsChanged.emit()

    def apply_changes(self, changes: dict) -> None:
        for path, v in changes.items():
            if path.startswith("exit."):
                apply_exit(self.s, int(path.split(".")[1]), v)
            elif path.startswith("basisrente."):
                set_basisrente_year(self.s, int(path.split(".")[1]), v)
            else:
                self.s.set(path, v)
        self.rebuild()  # optimiser proposals may add Gestaltungen
        self.settingsChanged.emit()
