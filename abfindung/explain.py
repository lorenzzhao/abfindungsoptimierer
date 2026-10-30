# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Structured explanation of a result (shared by the GUI explanation panel and the PDF report)."""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape

from .dates import fmt_eur, fmt_num
from .engine.trace import Traced, fmt_value
from .io.personal_model import HERKUNFT_LABEL

GROUP_ORDER = ["Übersicht", "Saldo", "Steuer", "Abfindung", "ALG", "KV", "Liquidität", "Rente", "Kalibrierung",
               "Hinweise und Warnungen"]


def group_rank(g: str) -> tuple:
    """Display order of result groups (GUI and PDF)."""
    for i, prefix in enumerate(GROUP_ORDER):
        if g.startswith(prefix):
            return (i, g)
    return (len(GROUP_ORDER), g)


FLAG_LABEL = {
    "fortgeschrieben": "fortgeschrieben",
    "ungeprueft": "Parameter ungeprüft",
    "unsicher": "unsicher",
    "warnung": "Warnung",
}


@dataclass
class SourceInfo:
    id: str
    text: str
    fundstelle: str
    url: str | None
    online_geprueft: bool | None
    art: str = ""


@dataclass
class RuleInfo:
    id: str
    bezeichnung: str
    beschreibung: str
    formel: str | None
    unsicherheit: str | None
    geprueft: bool
    quellen: list[SourceInfo] = field(default_factory=list)


@dataclass
class Explanation:
    id: str
    title: str
    value: str
    group: str
    flags: list[str]
    steps: list[str]
    inputs: list[tuple[str, str, str, str]]           # label, value, herkunft, xml path
    params: list[tuple[str, str, str, str, str, str]]  # id, bezeichnung, value, year, status, geprueft
    rules: list[RuleInfo]
    children: list[tuple[str, str, str]]              # id, label, value
    note: str = ""


def _fmt_param_value(v, einheit: str) -> str:
    if isinstance(v, bool):
        return "ja" if v else "nein"
    if isinstance(v, tuple):
        return f"{v[1]:02d}.{v[0]:02d}."
    if isinstance(v, (int, float)):
        if einheit == "Anteil":
            return fmt_num(v * 100, 3).rstrip("0").rstrip(",") + " %"
        if einheit.startswith("EUR"):
            return fmt_eur(v, 2) + ("/Monat" if einheit == "EUR_pro_Monat" else "/Jahr" if einheit == "EUR_pro_Jahr" else "")
        return fmt_num(v, 0) + (f" {einheit}" if einheit not in ("keine", "Anzahl") else "")
    return str(v)


def _fmt_input(v) -> str:
    if isinstance(v, bool):
        return "ja" if v else "nein"
    if isinstance(v, float):
        if abs(v) < 1 and v != 0:
            return fmt_num(v * 100, 2) + " %"
        return fmt_eur(v)
    if isinstance(v, int) and v > 20000:  # month index
        return f"{v % 12 + 1:02d}/{v // 12}"
    if hasattr(v, "strftime"):
        return v.strftime("%d.%m.%Y")
    return str(v)


def build(t: Traced, legal, rs) -> Explanation:
    params = []
    for pid, p in t.params.items():
        status = "fortgeschrieben" if p.fortgeschrieben else ""
        params.append((pid, p.bezeichnung, _fmt_param_value(p.value, p.einheit),
                       str(p.year_used) if p.year_used else "–", status, "geprüft" if p.geprueft else "ungeprüft"))
    rules = []
    for rid in t.rules:
        r = legal.rule(rid)
        if not r:
            continue
        srcs = []
        for q in r.quellen:
            src = legal.source(q.quelle)
            srcs.append(SourceInfo(q.quelle, q.text, src.fundstelle if src else q.quelle, src.url if src else None,
                                   src.online_geprueft if src else None, src.art if src else ""))
        rules.append(RuleInfo(r.id, r.bezeichnung, r.beschreibung, r.formel, r.unsicherheit, r.geprueft, srcs))
    children = [(c, rs[c].label, rs[c].fmt()) for c in t.children if c in rs]
    inputs = [(i.label, _fmt_input(i.value), HERKUNFT_LABEL.get(i.herkunft, i.herkunft), i.path) for i in t.inputs]
    flags = [FLAG_LABEL.get(f, f) for f in sorted(t.flags)]
    return Explanation(t.id, t.label, t.fmt(), t.group, flags, list(t.steps), inputs, params, rules, children, t.note)


def to_html(e: Explanation, colors: dict) -> str:
    """HTML for QTextBrowser. Links ``focus:<id>`` switch the focus."""
    c = colors
    h = []
    h.append(f"<h2 style='margin-bottom:2px'>{escape(e.title)}</h2>")
    h.append(f"<div style='font-size:18pt; font-weight:bold; color:{c['accent']}'>{escape(e.value)}</div>")
    if e.flags:
        h.append("<p>" + " ".join(
            f"<span style='background:{c['warn_bg']}; color:{c['warn_fg']}'>&nbsp;{escape(f)}&nbsp;</span>" for f in e.flags) + "</p>")
    h.append(f"<p style='color:{c['muted']}'>Bereich: {escape(e.group)} · ID <code>{escape(e.id)}</code></p>")
    if e.steps:
        h.append("<h3>Rechenweg</h3><ol>")
        for st in e.steps:
            h.append(f"<li>{escape(st)}</li>")
        h.append("</ol>")
    if e.note:
        h.append(f"<p><i>{escape(e.note)}</i></p>")
    if e.children:
        h.append("<h3>Abgeleitet aus</h3><ul>")
        for cid, lab, val in e.children:
            h.append(f"<li><a href='focus:{escape(cid)}'>{escape(lab)}</a>: {escape(val)}</li>")
        h.append("</ul>")
    if e.inputs:
        h.append("<h3>Eingangsdaten (persönlich / Einstellungen)</h3>")
        h.append(f"<table cellspacing='0' cellpadding='3' border='1' style='border-color:{c['border']}'>"
                 "<tr><th>Wert</th><th>Inhalt</th><th>Herkunft</th><th>Quelle in der XML</th></tr>")
        for lab, val, herk, path in e.inputs:
            col = c["warn_fg"] if herk == "Annahme" else c["text"]
            h.append(f"<tr><td>{escape(lab)}</td><td>{escape(val)}</td><td style='color:{col}'>{escape(herk)}</td>"
                     f"<td><code>{escape(path) or '–'}</code></td></tr>")
        h.append("</table>")
    if e.params:
        h.append("<h3>Rechtliche Parameter</h3>")
        h.append(f"<table cellspacing='0' cellpadding='3' border='1' style='border-color:{c['border']}'>"
                 "<tr><th>Parameter</th><th>Bezeichnung</th><th>Wert</th><th>Jahr</th><th>Status</th></tr>")
        for pid, bez, val, year, status, gep in e.params:
            st = ", ".join(x for x in (status, gep) if x)
            col = c["warn_fg"] if ("ungeprüft" in st or "fortgeschrieben" in st) else c["text"]
            h.append(f"<tr><td><code>{escape(pid)}</code></td><td>{escape(bez)}</td><td>{escape(val)}</td>"
                     f"<td>{escape(year)}</td><td style='color:{col}'>{escape(st)}</td></tr>")
        h.append("</table>")
    if e.rules:
        h.append("<h3>Regeln und Rechtsgrundlagen</h3>")
        unchecked = f" <span style='color:{c['warn_fg']}'>(ungeprüft)</span>"
        for r in e.rules:
            h.append(f"<p><b>{escape(r.id)}</b> – {escape(r.bezeichnung)}{'' if r.geprueft else unchecked}<br/>"
                     f"{escape(r.beschreibung)}</p>")
            if r.formel:
                h.append(f"<pre style='background:{c['code_bg']}'>{escape(r.formel)}</pre>")
            if r.unsicherheit:
                h.append(f"<p style='color:{c['warn_fg']}'>Unsicherheit: {escape(r.unsicherheit)}</p>")
            if r.quellen:
                h.append("<ul>")
                for q in r.quellen:
                    link = f" – <a href='{escape(q.url)}'>{escape(q.url)}</a>" if q.url else ""
                    chk = "online geprüft" if q.online_geprueft else "nicht online geprüft"
                    h.append(f"<li>{escape(q.text)} ({escape(q.fundstelle)}; {chk}){link}</li>")
                h.append("</ul>")
    return "\n".join(h)
