# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Command line: python -m abfindung.cli persoenlich.xml recht.xml [--optimize]

Prints the results as JSON (all values with label, unit and group; warnings). Exit code 2 on validation errors.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from . import DISCLAIMER, HAFTUNG, LEGAL_XML
from . import legal as legal_info
from .engine.optimizer import optimize
from .engine.scenario import run
from .engine.settings import from_personal
from .io import ValidationError, load_legal, load_personal


def _json_value(v):
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, float):
        return round(v, 2)
    return v


def build_report(pd, legal, do_opt: bool = False) -> dict:
    s = from_personal(pd, legal)
    r = run(s, legal)
    out = {
        "hinweis": DISCLAIMER,
        "haftungsausschluss": HAFTUNG,
        "horizont": [r.years[0], r.years[-1]],
        "saldo": round(r.saldo, 2),
        "jahre": {
            str(y): {
                "saldo": round(r.saldo_by_year[y], 2), "steuer": round(r.tax_by_year[y], 2),
                "alg": round(r.alg_by_year[y], 2), "kv_eigen": round(r.kv_by_year[y], 2),
                "aufwand": round(r.cost_by_year[y], 2), "gehalt_netto_sv": round(r.salary_by_year[y], 2),
            } for y in r.years
        },
        "gebunden": round(r.gebunden, 2),
        "liquiditaet_tiefpunkt": round(r.liq_min, 2),
        "ergebnisse": {
            t.id: {"bezeichnung": t.label, "wert": _json_value(t.value), "einheit": t.unit, "gruppe": t.group,
                   "regeln": t.rules, "parameter": sorted(t.params), "rechenweg": t.steps}
            for t in r.rs.values()
        },
        "warnungen": [{"text": w, "regeln": rules} for w, rules in r.warnings],
    }
    if do_opt:
        top, cur = optimize(s, legal)
        out["optimierung"] = {
            "aktuell": round(cur.saldo, 2),
            "top": [{"saldo": round(c.saldo, 2), "beschreibung": c.label, "aenderungen": {k: _json_value(v) for k, v in c.changes.items()},
                     "steuer": {str(k): round(v, 2) for k, v in c.tax_by_year.items()}, "alg": round(c.alg, 2),
                     "kv": round(c.kv, 2), "gebunden": round(c.gebunden, 2), "begruendung": c.explanation,
                     "regeln": c.rules} for c in top],
        }
    return out


def _utf8_streams() -> None:
    """Always write UTF-8: on Windows a redirected stdout/stderr uses the ANSI code page (cp1252), which cannot
    encode characters such as "−" in the JSON output."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):  # replaced by a stream without reconfigure()
            pass


def main(argv=None) -> int:
    _utf8_streams()
    ap = argparse.ArgumentParser(description="Abfindungsoptimierer (Kommandozeile)",
                                 formatter_class=argparse.RawTextHelpFormatter)  # keeps the lines of --version
    ap.add_argument("--version", action="version", version=legal_info.version_text(ap.prog),
                    help="Version, Copyright und Lizenz anzeigen")
    ap.add_argument("persoenlich", help="persönliche Daten (XML)")
    ap.add_argument("--optimize", action="store_true", help="Optimierung (Top 5) ausführen")
    ap.add_argument("--compact", action="store_true", help="ohne Rechenwege ausgeben")
    ap.add_argument("--pdf", metavar="DATEI", help="zusätzlich einen PDF-Bericht schreiben")
    a = ap.parse_args(argv)
    try:
        legal = load_legal(LEGAL_XML)
        pd = load_personal(a.persoenlich)
    except ValidationError as e:
        print(e.pretty(), file=sys.stderr)
        return 2
    rep = build_report(pd, legal, a.optimize)
    if a.pdf:
        from .report.pdf_export import export_pdf

        s = from_personal(pd, legal)
        top = optimize(s, legal)[0] if a.optimize else None
        export_pdf(a.pdf, run(s, legal), legal, optimizer_top=top, personal_path=a.persoenlich)
        print(f"PDF geschrieben: {a.pdf}", file=sys.stderr)
    if a.compact:
        for v in rep["ergebnisse"].values():
            v.pop("rechenweg", None)
    json.dump(rep, sys.stdout, ensure_ascii=False, indent=2)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
