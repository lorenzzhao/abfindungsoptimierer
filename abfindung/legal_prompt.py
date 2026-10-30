# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Prompt for checking the loaded legal rules in an AI chat and correcting them in line with the schema.

The prompt contains the legal XML file exactly as loaded, the XSD it must conform to, the years the planning uses
and the parameters the calculation relies on. It contains no personal data: only the legal file is included.
This module does not import Qt.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from .io.xml_loader import LEGAL_XSD


def _unchecked(legal) -> list[str]:
    out = []
    for pid, entries in sorted(legal.params.items()):
        for e in entries:
            if not e.geprueft:
                years = f"{e.gueltig_ab or '…'}–{e.gueltig_bis or '…'}"
                out.append(f"{pid} ({e.bezeichnung}; gültig {years})")
    return out


def build_prompt(legal, years: list[int] | None = None, used_params: list[str] | None = None,
                 today: date | None = None) -> str:
    """Return the prompt text. ``years``: years of the planning horizon; ``used_params``: parameter ids the
    current calculation reads (checked first)."""
    today = today or date.today()
    xml = Path(legal.path).read_text(encoding="utf-8")
    xsd = LEGAL_XSD.read_text(encoding="utf-8")
    years = sorted(set(years or []))
    year_txt = f"{years[0]}–{years[-1]}" if years else "die in der Datei genannten Jahre"
    used = sorted(set(used_params or []))
    unchecked = _unchecked(legal)
    tariff_years = sorted(legal.tariffs)
    missing_tariffs = [y for y in years if y not in legal.tariffs]

    parts = [
        "# Aufgabe: Rechtliche Vorgaben für den Abfindungsoptimierer prüfen und korrigieren",
        "",
        "Du bist Expertin bzw. Experte für deutsches Einkommensteuer-, Sozialversicherungs- und Arbeitsförderungsrecht "
        "(EStG, SGB III, SGB V, SGB XI, KSchG/BGB). Unten steht eine XML-Datei mit den rechtlichen Werten "
        "(Parameter, Tabellen, Steuertarife, Regeln und Quellen), mit denen ein Planungsprogramm für Abfindungen, "
        "Arbeitslosengeld und Krankenversicherung rechnet, sowie das XML-Schema (XSD), dem die Datei entsprechen muss.",
        "",
        f"Heutiges Datum: {today:%d.%m.%Y}. Stand laut Datei: {legal.stand or 'nicht angegeben'}"
        + (f" ({legal.rechtsstand})" if legal.rechtsstand else "") + ".",
        f"Die Planung rechnet mit den Jahren {year_txt}.",
        "",
        "## Was zu tun ist",
        "",
        "1. Prüfe jeden Wert auf seine Richtigkeit für die Jahre der Planung: Beträge, Sätze, Grenzen, Fristen, "
        "Tabellen (z. B. ALG-Anspruchsdauer, Kündigungsfristen, PV-Kinderabschläge) und die Koeffizienten des "
        "Einkommensteuertarifs nach § 32a EStG. Beachte die Gültigkeitsjahre (Attribute gueltigAbJahr/gueltigBisJahr).",
        "2. Prüfe die Regeln (Beschreibung, Formel, Unsicherheit) auf fachliche Richtigkeit und die Quellen "
        "(Fundstellen, URLs) auf Aktualität.",
        "3. Ergänze fehlende Jahreswerte, soweit sie amtlich feststehen (z. B. ein neuer Tarif oder neue "
        "Beitragsbemessungsgrenzen), als zusätzliche Einträge mit passendem gueltigAbJahr. Werte, die noch nicht "
        "feststehen, nicht erfinden: dann den bisherigen Wert lassen und das in Hinweis/Unsicherheit vermerken.",
        "4. Setze geprueft=\"true\" nur bei Werten, die du anhand einer konkreten, genannten amtlichen Quelle "
        "bestätigt hast, und trage diese Quelle ein. Was du nicht sicher belegen kannst, bleibt geprueft=\"false\".",
        "5. Wenn du keinen Zugriff auf aktuelle Quellen hast, sage das ausdrücklich und ändere dann nur offensichtliche "
        "Fehler.",
        "",
        "## Regeln für die geänderte Datei",
        "",
        "- Die Datei muss gegen das unten stehende XSD gültig bleiben (Namespace urn:abfindung:recht:v1, Reihenfolge "
        "und Pflichtelemente beachten). Das Programm lehnt ungültige Dateien beim Laden ab.",
        "- IDs von Parametern, Tabellen, Regeln und Quellen nicht umbenennen oder entfernen – das Programm greift über "
        "diese IDs auf die Werte zu. Neue IDs nur zusätzlich anlegen.",
        "- Einheiten und Werttypen (Attribute einheit/wertTyp) beibehalten; Anteile als Dezimalzahl (0.146 statt "
        "14,6 %), Dezimalpunkt statt Komma, Beträge in Euro.",
        "- Metadaten/Stand auf das heutige Datum setzen und unter Rechtsstand kurz festhalten, für welche Jahre die "
        "Werte gelten.",
        "",
        "## Gewünschte Antwort",
        "",
        "1. Eine Tabelle aller Änderungen: ID, alter Wert, neuer Wert, Begründung, Quelle.",
        "2. Eine Liste der Werte, die du nicht prüfen konntest, und offene Rechtsfragen.",
        "3. Die vollständige geänderte XML-Datei in einem einzigen Codeblock (```xml … ```), ohne Auslassungen "
        "(keine „…“ oder „Rest unverändert“), damit sie direkt gespeichert und im Programm geladen werden kann.",
        "",
        "## Hinweise zur Priorität",
        "",
    ]
    if used:
        parts.append("Diese Parameter verwendet die aktuelle Berechnung – bitte zuerst und besonders sorgfältig prüfen:")
        parts.append(", ".join(used))
        parts.append("")
    if unchecked:
        parts.append(f"Diese {len(unchecked)} Parametereinträge sind in der Datei als ungeprüft markiert "
                     "(geprueft=\"false\"):")
        parts += [f"- {u}" for u in unchecked]
        parts.append("")
    parts.append("Vorhandene Einkommensteuertarife: " + (", ".join(map(str, tariff_years)) or "keine") + ".")
    if missing_tariffs:
        parts.append("Für " + ", ".join(map(str, missing_tariffs)) + " fehlt ein Tarif; das Programm schreibt den "
                     "letzten fort. Bitte ergänzen, sofern der Tarif amtlich feststeht.")
    parts += [
        "",
        "Hinweis: Die Datei enthält keine persönlichen Daten; bitte auch in der Antwort keine annehmen oder ergänzen.",
        "",
        f"## Aktuelle Datei ({Path(legal.path).name})",
        "",
        "```xml",
        xml.rstrip(),
        "```",
        "",
        "## XML-Schema (regulatory_input.xsd)",
        "",
        "```xml",
        xsd.rstrip(),
        "```",
        "",
    ]
    return "\n".join(parts)
