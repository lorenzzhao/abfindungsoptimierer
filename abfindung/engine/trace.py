# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Traceable results.

Every value the engine produces is a :class:`Traced`: the value plus the calculation
steps (with the numbers inserted), the legal parameters used (with year and
"fortgeschrieben" flag), the rule ids (``R_...``), the personal inputs it is based on
(with their ``herkunft``) and the ids of other results it is derived from.
The GUI explanation panel and the PDF report are rendered from these objects.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date

from ..dates import fmt_date, fmt_eur, fmt_num, fmt_pct


@dataclass
class ParamRef:
    id: str
    value: object
    year_used: int | None
    fortgeschrieben: bool
    bezeichnung: str
    einheit: str
    geprueft: bool


@dataclass
class InputRef:
    label: str
    value: object
    herkunft: str
    path: str = ""
    setting: str = ""  # settings path of the input field (empty for values not set in the program)


@dataclass
class Traced:
    id: str
    label: str
    value: object
    unit: str = "EUR"
    group: str = ""
    steps: list[str] = field(default_factory=list)
    params: dict[str, ParamRef] = field(default_factory=dict)
    rules: list[str] = field(default_factory=list)
    inputs: list[InputRef] = field(default_factory=list)
    children: list[str] = field(default_factory=list)
    flags: set[str] = field(default_factory=set)
    note: str = ""

    def fmt(self) -> str:
        return fmt_value(self.value, self.unit)

    @property
    def uncertain(self) -> bool:
        return bool(self.flags & {"unsicher", "fortgeschrieben", "ungeprueft"}) or any(
            i.herkunft == "annahme" for i in self.inputs)


def fmt_value(v, unit: str) -> str:
    if v is None:
        return "–"
    if unit == "EUR":
        return fmt_eur(v)
    if unit == "EUR2":
        return fmt_eur(v, 2)
    if unit == "Anteil":
        return fmt_pct(v)
    if unit == "Datum":
        return fmt_date(v) if isinstance(v, date) else str(v)
    if unit in ("Tage", "Monate", "Anzahl", "Wochen", "Jahre"):
        return f"{fmt_num(v, 0)} {unit if unit != 'Anzahl' else ''}".strip()
    if unit == "bool":
        return "ja" if v else "nein"
    return str(v)


class ResultSet(OrderedDict):
    def add(self, t: Traced) -> Traced:
        self[t.id] = t
        return t


class Tracer:
    """Factory for trace builders; holds the legal data and the settings (for origins)."""

    def __init__(self, legal, settings=None):
        self.legal = legal
        self.settings = settings
        self.used_params: dict[str, ParamRef] = {}
        self.used_rules: set[str] = set()
        self.derived: dict = {}  # settings path -> (value, trace id) for values derived by the program

    def new(self, id: str, label: str, unit: str = "EUR", group: str = "") -> "TB":
        return TB(self, id, label, unit, group)

    def p(self, pid: str, year: int | None = None):
        """Parameter lookup without a result (still recorded as used)."""
        pv = self.legal.param(pid, year)
        self._record(pv)
        return pv.value

    def _record(self, pv) -> ParamRef:
        ref = ParamRef(pv.id, pv.value, pv.year_used, pv.fortgeschrieben, pv.entry.bezeichnung,
                       pv.entry.einheit, pv.entry.geprueft)
        key = f"{pv.id}@{pv.year_requested}"
        self.used_params.setdefault(key, ref)
        return ref


class TB:
    """Builder for one :class:`Traced` result."""

    def __init__(self, tracer: Tracer, id, label, unit, group):
        self.tr = tracer
        self.t = Traced(id, label, None, unit, group)

    @property
    def legal(self):
        return self.tr.legal

    def p(self, pid: str, year: int | None = None):
        pv = self.tr.legal.param(pid, year)
        ref = self.tr._record(pv)
        self.t.params[pid] = ref
        if pv.fortgeschrieben:
            self.t.flags.add("fortgeschrieben")
        if not pv.entry.geprueft:
            self.t.flags.add("ungeprueft")
        return pv.value

    def rule(self, *ids: str) -> "TB":
        for r in ids:
            if r not in self.t.rules:
                self.t.rules.append(r)
            self.tr.used_rules.add(r)
        return self

    def step(self, text: str) -> "TB":
        self.t.steps.append(text)
        return self

    def child(self, *ids: str) -> "TB":
        for i in ids:
            if i and i not in self.t.children:
                self.t.children.append(i)
        return self

    def inp(self, label: str, value, herkunft: str = "berechnet", path: str = "", setting: str = "") -> "TB":
        self.t.inputs.append(InputRef(label, value, herkunft, path, setting))
        return self

    def s(self, path: str, label: str):
        """Reference a settings value by its path and return it."""
        st = self.tr.settings
        value = st.get(path)
        self.inp(label, value, st.origin_of(path), st.xml_path_of(path), path)
        d = self.tr.derived.get(path)
        if d and d[1] != self.t.id:
            self.child(d[1])
        return value

    def flag(self, *f: str) -> "TB":
        self.t.flags.update(f)
        return self

    def note(self, text: str) -> "TB":
        self.t.note = (self.t.note + " " + text).strip()
        return self

    def done(self, value) -> Traced:
        self.t.value = value
        return self.t
