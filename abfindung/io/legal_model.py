# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Data model for the legal input file (namespace urn:abfindung:recht:v1).

Every legal figure used by the engine is looked up here via :meth:`LegalData.param`.
If no value exists for the requested year, the latest earlier value is used and the
result is flagged as ``fortgeschrieben`` (carried forward).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

from lxml import etree

NS = {"r": "urn:abfindung:recht:v1"}


class MissingParameter(KeyError):
    pass


@dataclass
class Source:
    id: str
    art: str
    fundstelle: str
    url: str | None
    online_geprueft: bool


@dataclass
class SourceRef:
    quelle: str
    text: str


@dataclass
class Rule:
    id: str
    bereich: str
    geprueft: bool
    bezeichnung: str
    beschreibung: str
    formel: str | None
    quellen: list[SourceRef]
    unsicherheit: str | None


@dataclass
class ParamEntry:
    id: str
    bereich: str
    wert_typ: str
    einheit: str
    gueltig_ab: int | None
    gueltig_bis: int | None
    geprueft: bool
    bezeichnung: str
    raw: str
    value: object
    quellen: list[SourceRef]
    hinweis: str | None


@dataclass
class ParamValue:
    id: str
    value: object
    year_requested: int | None
    year_used: int | None
    fortgeschrieben: bool
    entry: ParamEntry


@dataclass
class TariffZone:
    nr: int
    typ: str
    lower: Decimal
    upper: Decimal | None
    formel: str
    coeffs: dict[str, Decimal]
    offset: Decimal  # value subtracted from zvE in the progression formula


@dataclass
class TariffDef:
    year: int
    geprueft: bool
    fortschreibung: bool
    zones: list[TariffZone]
    rundung: str
    splitting: str
    quellen: list[SourceRef]


@dataclass
class Table:
    id: str
    bereich: str
    geprueft: bool
    bezeichnung: str
    columns: list[tuple[str, str]]
    rows: list[dict[str, float]]
    quellen: list[SourceRef]
    hinweis: str | None


@dataclass
class LegalData:
    beschreibung: str = ""
    stand: str = ""
    rechtsstand: str = ""
    hinweise: list[str] = field(default_factory=list)
    tariffs: dict[int, TariffDef] = field(default_factory=dict)
    params: dict[str, list[ParamEntry]] = field(default_factory=dict)
    tables: dict[str, Table] = field(default_factory=dict)
    rules: dict[str, Rule] = field(default_factory=dict)
    sources: dict[str, Source] = field(default_factory=dict)
    path: str = ""

    # -- parameters -------------------------------------------------------
    def has(self, pid: str) -> bool:
        return pid in self.params

    def pick(self, *pids: str) -> str | None:
        """First of several alternative parameter ids that exists (e.g. renamed parameters)."""
        return next((p for p in pids if p in self.params), None)

    def param(self, pid: str, year: int | None = None) -> ParamValue:
        entries = self.params.get(pid)
        if not entries:
            raise MissingParameter(f"Parameter „{pid}“ fehlt in den rechtlichen Vorgaben.")
        if year is None:
            e = max(entries, key=lambda x: x.gueltig_ab or 0)
            return ParamValue(pid, e.value, None, e.gueltig_ab, False, e)
        valid = [
            e for e in entries
            if (e.gueltig_ab is None or e.gueltig_ab <= year)
            and (e.gueltig_bis is None or e.gueltig_bis >= year)
        ]
        if valid:
            e = max(valid, key=lambda x: x.gueltig_ab or 0)
            # A value tied to a specific year is carried forward for later years.
            fortg = e.gueltig_ab is not None and year > e.gueltig_ab and e.gueltig_bis is None
            return ParamValue(pid, e.value, year, e.gueltig_ab, fortg, e)
        earlier = [e for e in entries if e.gueltig_ab is not None and e.gueltig_ab <= year]
        if earlier:
            e = max(earlier, key=lambda x: x.gueltig_ab or 0)
        else:  # only later values exist: use the earliest one
            e = min(entries, key=lambda x: x.gueltig_ab or 0)
        return ParamValue(pid, e.value, year, e.gueltig_ab, True, e)

    def value(self, pid: str, year: int | None = None):
        return self.param(pid, year).value

    def tariff(self, year: int) -> tuple[TariffDef, bool]:
        if not self.tariffs:
            raise MissingParameter("Kein Einkommensteuertarif in den rechtlichen Vorgaben.")
        if year in self.tariffs:
            return self.tariffs[year], False
        earlier = [y for y in self.tariffs if y < year]
        y = max(earlier) if earlier else min(self.tariffs)
        return self.tariffs[y], True

    def table(self, tid: str) -> Table:
        if tid not in self.tables:
            raise MissingParameter(f"Tabelle „{tid}“ fehlt in den rechtlichen Vorgaben.")
        return self.tables[tid]

    def rule(self, rid: str) -> Rule | None:
        return self.rules.get(rid)

    def source(self, sid: str) -> Source | None:
        return self.sources.get(sid)


# -- parsing -----------------------------------------------------------------

def _t(el, path: str) -> str | None:
    v = el.findtext(path, namespaces=NS)
    return v.strip() if v is not None else None


def _bool(s: str | None, default: bool = False) -> bool:
    if s is None:
        return default
    return s.strip().lower() in ("true", "1")


def _refs(el) -> list[SourceRef]:
    return [SourceRef(q.get("quelle"), (q.text or "").strip()) for q in el.findall("r:Quellenverweis", NS)]


def _parse_value(raw: str, wert_typ: str):
    raw = raw.strip()
    if wert_typ == "decimal":
        return float(raw)
    if wert_typ == "integer":
        return int(float(raw))
    if wert_typ == "boolean":
        return _bool(raw)
    if wert_typ == "monatTag":
        m = re.match(r"--(\d\d)-(\d\d)", raw)
        return (int(m.group(1)), int(m.group(2))) if m else raw
    return raw


def _zone(el) -> TariffZone:
    coeffs = {c.get("name"): Decimal(c.text.strip()) for c in el.findall("r:Koeffizient", NS)}
    lower = Decimal(_t(el, "r:Untergrenze"))
    upper_s = _t(el, "r:Obergrenze")
    formel = _t(el, "r:Formel") or ""
    m = re.search(r"zvE\s*-\s*([\d.]+)\s*\)", formel)
    offset = Decimal(m.group(1)) if m else lower - 1
    return TariffZone(
        nr=int(el.get("nr")), typ=el.get("typ"), lower=lower,
        upper=Decimal(upper_s) if upper_s else None, formel=formel, coeffs=coeffs, offset=offset,
    )


def parse_legal(root: etree._Element) -> LegalData:
    d = LegalData()
    meta = root.find("r:Metadaten", NS)
    d.beschreibung = _t(meta, "r:Beschreibung") or ""
    d.stand = _t(meta, "r:Stand") or ""
    d.rechtsstand = _t(meta, "r:Rechtsstand") or ""
    d.hinweise = [(h.text or "").strip() for h in meta.findall("r:Hinweis", NS)]

    for t in root.findall("r:Einkommensteuertarif", NS):
        td = TariffDef(
            year=int(t.get("jahr")), geprueft=_bool(t.get("geprueft")),
            fortschreibung=_bool(t.get("fortschreibungFuerFolgejahr")),
            zones=sorted((_zone(z) for z in t.findall("r:Zone", NS)), key=lambda z: z.nr),
            rundung=_t(t, "r:Rundung") or "", splitting=_t(t, "r:Splittingverfahren") or "",
            quellen=_refs(t),
        )
        d.tariffs[td.year] = td

    for p in root.findall("r:Parameter/r:Param", NS):
        raw = _t(p, "r:Wert") or ""
        e = ParamEntry(
            id=p.get("id"), bereich=p.get("bereich"), wert_typ=p.get("wertTyp"), einheit=p.get("einheit"),
            gueltig_ab=int(p.get("gueltigAbJahr")) if p.get("gueltigAbJahr") else None,
            gueltig_bis=int(p.get("gueltigBisJahr")) if p.get("gueltigBisJahr") else None,
            geprueft=_bool(p.get("geprueft")), bezeichnung=_t(p, "r:Bezeichnung") or "",
            raw=raw, value=_parse_value(raw, p.get("wertTyp")), quellen=_refs(p), hinweis=_t(p, "r:Hinweis"),
        )
        d.params.setdefault(e.id, []).append(e)

    for t in root.findall("r:Tabellen/r:Tabelle", NS):
        rows = []
        for z in t.findall("r:Zeile", NS):
            rows.append({c.get("spalte"): float(c.text) for c in z.findall("r:Zelle", NS)})
        d.tables[t.get("id")] = Table(
            id=t.get("id"), bereich=t.get("bereich"), geprueft=_bool(t.get("geprueft")),
            bezeichnung=_t(t, "r:Bezeichnung") or "",
            columns=[(s.get("name"), s.get("einheit")) for s in t.findall("r:Spalte", NS)],
            rows=rows, quellen=_refs(t), hinweis=_t(t, "r:Hinweis"),
        )

    for r in root.findall("r:Regeln/r:Regel", NS):
        d.rules[r.get("id")] = Rule(
            id=r.get("id"), bereich=r.get("bereich"), geprueft=_bool(r.get("geprueft")),
            bezeichnung=_t(r, "r:Bezeichnung") or "", beschreibung=_t(r, "r:Beschreibung") or "",
            formel=_t(r, "r:Formel"), quellen=_refs(r), unsicherheit=_t(r, "r:Unsicherheit"),
        )

    for q in root.findall("r:Quellen/r:Quelle", NS):
        d.sources[q.get("id")] = Source(
            id=q.get("id"), art=q.get("art"), fundstelle=_t(q, "r:Fundstelle") or "",
            url=_t(q, "r:Url"), online_geprueft=_bool(q.get("onlineGeprueft")),
        )
    return d
