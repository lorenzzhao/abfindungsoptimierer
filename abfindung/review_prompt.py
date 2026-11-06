# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Prompt for an independent check of the whole calculation in an AI chat.

The prompt contains every input with the place where it is set in the program (tab › group › field), every
calculated value with its meaning, calculation steps, inputs, legal parameters and rules, the hints, and the
loaded legal rules. The AI is asked to name each problem with the place in the program, so it can be found and
corrected there. Unlike the prompt for the legal rules it contains the personal data of the planning.
This module does not import Qt.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from .dates import fmt_num
from .explain import HERKUNFT_LABEL, _fmt_input, build, group_sort_key

_TAG = re.compile(r"<[^>]+>")


def _plain(text: str) -> str:
    return " ".join(_TAG.sub("", str(text)).replace("&nbsp;", " ").replace("&amp;", "&").split())


def _cell(text) -> str:
    return _plain(text).replace("|", "/") or "–"


def _value(v, path: str = "") -> str:
    if v is None:
        return "–"
    if isinstance(v, bool):
        return "ja" if v else "nein"
    if isinstance(v, float):
        return fmt_num(v, 2 if v != int(v) else 0) if abs(v) >= 1 or v == 0 else fmt_num(v, 4)
    if isinstance(v, int):
        return f"{v % 12 + 1:02d}/{v // 12}" if path.endswith("_idx") else str(v)  # month index
    if hasattr(v, "strftime"):
        return v.strftime("%d.%m.%Y")
    return str(v)


def place(row: dict) -> str:
    """Where an input is set: "Eingaben › tab › group › field"."""
    return " › ".join(["Eingaben", row["tab"] or "?", *row["groups"], _plain(row["label"]) or row["path"]])


def build_prompt(res, legal, inputs: list[dict], today: date | None = None) -> str:
    """Return the prompt text. ``inputs``: rows of :meth:`InputsPanel.locations` (path, tab, groups, label,
    value, origin, xml, active)."""
    today = today or date.today()
    s = res.settings
    o = s.options
    nr = {row["path"]: f"E{i}" for i, row in enumerate(inputs, 1)}
    rows = [t for t in res.rs.values() if not t.id.startswith("_")]
    key = group_sort_key(s)
    rows.sort(key=lambda t: key(t.group or "Übersicht"))

    parts = [
        "# Aufgabe: Berechnung des Abfindungsoptimierers unabhängig prüfen",
        "",
        "Du bist Expertin bzw. Experte für deutsches Einkommensteuer-, Sozialversicherungs- und "
        "Arbeitsförderungsrecht (EStG, SGB III, SGB V, SGB XI, KSchG/BGB). Ein Planungsprogramm hat für einen "
        "Haushalt die Steuer, das Arbeitslosengeld (ALG), die Kranken- und Pflegeversicherung und den Netto-Saldo "
        "rund um eine Abfindung berechnet. Prüfe die Eingaben, die Ergebnisse und die rechtlichen Vorgaben "
        "unabhängig vom Programm.",
        "",
        f"Heutiges Datum: {today:%d.%m.%Y}. Planungshorizont: {o.horizon_start}–{o.horizon_end}"
        + (" (automatisch bestimmt)" if o.horizon_auto else "") + f". Netto-Saldo laut Programm: {res.rs['saldo'].fmt()}.",
        f"Rechtliche Vorgaben: Stand {legal.stand or 'nicht angegeben'}"
        + (f" ({legal.rechtsstand})" if legal.rechtsstand else "") + ".",
        "",
        "## Was zu tun ist",
        "",
        "1. **Eingaben**: Sind sie in sich stimmig und plausibel (z. B. Daten, Fristen, Beträge, Jahreswerte, "
        "Schalter wie Austritt/ALG/KV, Familienstand und Kinder)? Fehlen Angaben, die für die Berechnung nötig sind? "
        "Widersprechen sich Eingaben?",
        "2. **Ergebnisse**: Rechne die wichtigsten Werte nach (zu versteuerndes Einkommen, Einkommensteuer mit "
        "Fünftelregelung nach § 34 EStG und Progressionsvorbehalt nach § 32b EStG, Soli, Kirchensteuer, "
        "ALG-Höhe, -Dauer, Sperrzeit und Ruhen nach §§ 157, 158, 159 SGB III, KV/PV-Beiträge, Netto-Saldo). Prüfe, ob "
        "die Rechenschritte zu den Eingaben und Parametern passen und ob die Ergebnisse untereinander konsistent sind.",
        "3. **Rechtliche Vorgaben**: Sind die verwendeten Parameter, Tarife und Regeln für die Jahre der Planung "
        "richtig? Wird eine Regel falsch angewendet oder fehlt eine, die hier greift?",
        "4. **Gestaltung**: Weise auf rechtliche Risiken oder übersehene Möglichkeiten hin, soweit sie sich aus den "
        "Daten ergeben. Keine Steuer- oder Rechtsberatung im Einzelfall – nur Prüfhinweise.",
        "",
        "Rechne selbst nach und übernimm nichts ungeprüft aus dem Programm. Wenn du etwas nicht prüfen kannst "
        "(z. B. ohne Zugriff auf aktuelle Quellen), sage das.",
        "",
        "## Wie du auf Stellen im Programm verweist",
        "",
        "- Eingaben haben eine Nummer (E1, E2, …) und einen **Ort im Programm** in der Form "
        "„Eingaben › Reiter › Gruppe › Feld“. Dort ändert man den Wert im Programm.",
        "- Ergebnisse haben eine **ID** (z. B. est_2027) und stehen unter „Ergebnisse › Bereich › Bezeichnung“; bei "
        "jedem Ergebnis steht, aus welchen Eingaben (E-Nummern) es berechnet wird.",
        "- Rechtliche Parameter haben eine Parameter-ID (z. B. est_grundfreibetrag); sie stehen in der Datei der "
        "rechtlichen Vorgaben (unten) und werden über Datei → Rechtliche Vorgaben öffnen geladen.",
        "- Ist ein Ergebnis falsch, weil eine Eingabe falsch ist, nenne die Eingabe (E-Nummer und Ort) als Ursache.",
        "",
        "## Gewünschte Antwort",
        "",
        "1. Eine Tabelle aller Befunde, wichtigste zuerst, mit den Spalten: Nr. | Schwere (Fehler / Inkonsistenz / "
        "Unplausibel / Hinweis) | Ort im Programm (E-Nummer und Ort, Ergebnis-ID oder Parameter-ID) | Wert im Programm | "
        "Befund | richtiger Wert bzw. Vorschlag | Rechtsgrundlage/Quelle.",
        "2. Eine kurze Liste der Werte, die du nachgerechnet und als richtig bestätigt hast.",
        "3. Offene Fragen und Werte, die du nicht prüfen konntest.",
        "",
        "Die Daten unten sind die vollständigen Angaben zu dieser Planung. Erfinde keine weiteren Angaben; wenn "
        "etwas fehlt, frage nach oder nenne es unter Punkt 3.",
        "",
        "## A. Eingaben",
        "",
        "Spalten: Nr. | Ort im Programm | Wert | Herkunft | geht in die Berechnung ein | Einstellungspfad | Pfad in der "
        "XML-Datei der persönlichen Daten. „nein“ in der fünften Spalte: der Wert ist ausgegraut (z. B. Bereich "
        "abgeschaltet oder durch einen Schalter nicht relevant) und wird nicht verwendet.",
        "",
        "| Nr. | Ort im Programm | Wert | Herkunft | aktiv | Einstellungspfad | XML-Pfad |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in inputs:
        parts.append(f"| {nr[row['path']]} | {_cell(place(row))} | {_cell(_value(row['value'], row['path']))} | "
                     f"{_cell(HERKUNFT_LABEL.get(row['origin'], row['origin'] or '–'))} | "
                     f"{'ja' if row['active'] else 'nein'} | {_cell(row['path'])} | {_cell(row['xml'])} |")
    parts += ["", "## B. Ergebnisse", "",
              "Alle berechneten Werte, auch die, die im Programm gerade ausgeblendet sind. Je Ergebnis: Ort, Wert, "
              "Bedeutung, Rechenweg, Eingaben, rechtliche Parameter und Regeln, abgeleitet aus (IDs).", ""]
    for t in rows:
        e = build(t, legal, res.rs)
        parts.append(f"### {t.id}: {_plain(t.label)} = {t.fmt()}")
        parts.append(f"Ort: Ergebnisse › {t.group or 'Übersicht'} › {_plain(t.label)}"
                     + (f" · Kennzeichen: {', '.join(e.flags)}" if e.flags else ""))
        if e.meaning:
            parts.append(f"Bedeutung: {_plain(e.meaning)}")
        if e.steps:
            parts.append("Rechenweg:")
            parts += [f"- {_plain(x)}" for x in e.steps]
        if t.inputs:
            ins = []
            for i in t.inputs:
                ref = nr.get(i.setting)
                ins.append(f"{_plain(i.label)} = {_fmt_input(i.value)}"
                           f" ({HERKUNFT_LABEL.get(i.herkunft, i.herkunft)}" + (f", {ref}" if ref else "") + ")")
            parts.append("Eingaben: " + "; ".join(ins))
        if e.params:
            parts.append("Parameter: " + "; ".join(
                f"{pid} = {val} ({year}{', ' + status if status else ''}, {gep})"
                for pid, _bez, val, year, status, gep in e.params))
        if e.rules:
            parts.append("Regeln: " + ", ".join(f"{r.id} ({_plain(r.bezeichnung)})" for r in e.rules))
        if e.children:
            parts.append("Abgeleitet aus: " + ", ".join(c[0] for c in e.children))
        if e.note:
            parts.append(f"Hinweis: {_plain(e.note)}")
        parts.append("")
    parts += ["## C. Hinweise und Warnungen des Programms", ""]
    parts += [f"- {_plain(w)}" + (f" (Regeln: {', '.join(r)})" if r else "") for w, r in res.warnings] or ["- keine"]
    xml = Path(legal.path).read_text(encoding="utf-8")
    parts += [
        "",
        f"## D. Rechtliche Vorgaben ({Path(legal.path).name})",
        "",
        "Die Datei, mit der das Programm rechnet (Parameter mit Gültigkeitsjahren, Tabellen, Steuertarife, Regeln, "
        "Quellen). Ort im Programm: Datei → Rechtliche Vorgaben öffnen.",
        "",
        "```xml",
        xml.rstrip(),
        "```",
        "",
    ]
    return "\n".join(parts)
