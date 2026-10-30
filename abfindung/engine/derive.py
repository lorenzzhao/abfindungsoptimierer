# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Values the program determines itself when their origin (herkunft) is "abgeleitet".

Each derivation writes the value into the (effective) settings used for the run and records a trace;
``tracer.derived`` maps the settings path to ``(value, trace id)``. The GUI shows the value in the locked
input field and the trace steps in its tooltip. Later references to the value (``TB.s``) link the trace.

Derived per person (in this order, later ones use earlier results):
  kfrist_monate         notice period of the employer from T_Kuendigungsfristen_AG
  kv_status             compulsory / voluntary insurance from the salary and the Versicherungspflichtgrenze
  sperrzeit_wochen      wichtiger Grund (R_WichtigerGrund): severance 0.25–0.5 monthly salaries per year of
                        service and notice period kept → 0 weeks, otherwise the regular Sperrzeit
  arbeitsuchend_datum   latest date without a Sperrzeit for late registration (§ 38 SGB III)
  kv_beitrag_schaetzung voluntary KV/PV contribution per month (without severance) after the exit
The ALG amount (alg_monat) is derived in :func:`alg.alg_rate`, the Fünftelregelung in the scenario.
"""

from __future__ import annotations

from datetime import timedelta

from ..dates import fmt_date, fmt_eur, fmt_num, fmt_pct
from .health import kv_rate_voluntary
from .timeline import frist_from_table, melde_deadline, notice_end


def derives(s, path: str) -> bool:
    return s.origin_of(path) == "abgeleitet"


def _set(s, tracer, path: str, value, tb) -> None:
    s.set(path, value)
    tracer.derived[path] = (value, tb.t.id)


def derive_person(ps, idx: int, s, tracer, rs) -> None:
    base = f"persons.{idx}"
    lab = ps.label
    grp = f"Abgeleitete Werte – {lab}"

    path = f"{base}.kfrist_monate"
    if derives(s, path):
        tb = tracer.new(f"abl_{ps.id}_kfrist", f"Kündigungsfrist des Arbeitgebers {lab}", "Monate", grp)
        tb.rule("R_Ruhen158")
        bz = tb.s(f"{base}.bz_jahre", "Betriebszugehörigkeit (Jahre)")
        months = frist_from_table(bz, tb)
        tb.step(f"Gesetzliche Frist aus Tabelle T_Kuendigungsfristen_AG (§ 622 Abs. 2 BGB) bei {fmt_num(bz, 0)} Jahren "
                f"Betriebszugehörigkeit: {fmt_num(months, 0)} Monate zum Monatsende")
        tb.note("Eine längere vertragliche oder tarifliche Frist bitte als Angabe eintragen.")
        _set(s, tracer, path, months, tb)
        rs.add(tb.done(months))

    path = f"{base}.kv_status"
    if derives(s, path) and ps.kv_aktiv:
        tb = tracer.new(f"abl_{ps.id}_kvstatus", f"KV-Status vor dem Austritt {lab}", "Text", grp)
        tb.rule("R_KV_Freiwillig")
        y = ps.end_date.year if ps.austritt else s.options.horizon_start
        tb.s(f"{base}.salary.{y}", f"Bruttogehalt {y}")
        sal = ps.annual_equiv(y)
        vpg = tb.p("kv_versicherungspflichtgrenze", y)
        status = "freiwillig_gesetzlich" if sal > vpg else "pflichtversichert"
        tb.step(f"Jahresgehalt {y} (hochgerechnet auf ein volles Jahr) {fmt_eur(sal)} "
                f"{'>' if sal > vpg else '≤'} Versicherungspflichtgrenze {fmt_eur(vpg)} (§ 6 Abs. 1 Nr. 1 SGB V) → "
                + ("versicherungsfrei, freiwillig gesetzlich versichert" if sal > vpg else "pflichtversichert"))
        tb.step("Vereinfachung: Maßgeblich wäre das regelmäßige Entgelt im Vorjahr und im laufenden Jahr (§ 6 Abs. 4 SGB V). "
                "Eine private Versicherung oder eine Befreiung lässt sich nicht ableiten, sie bitte als Angabe eintragen.")
        tb.flag("unsicher")
        _set(s, tracer, path, status, tb)
        rs.add(tb.done(status))

    path = f"{base}.sperrzeit_wochen"
    if derives(s, path) and ps.austritt and ps.alg_aktiv:
        tb = tracer.new(f"abl_{ps.id}_sperrzeit", f"Erwartete Sperrzeit {lab}", "Wochen", grp)
        tb.rule("R_Sperrzeit", "R_WichtigerGrund")
        lo = tb.p("alg_wichtiger_grund_abfindung_min")
        hi = tb.p("alg_wichtiger_grund_abfindung_max")
        w12 = int(tb.p("alg_sperrzeit_arbeitsaufgabe_wochen"))
        abf = tb.s(f"{base}.severance", "Abfindung (brutto)")
        bz = tb.s(f"{base}.bz_jahre", "Betriebszugehörigkeit (Jahre)")
        y = ps.end_date.year
        monat = ps.annual_equiv(y) / 12
        tb.s(f"{base}.salary.{y}", f"Bruttogehalt {y}")
        ratio = abf / (monat * bz) if monat > 0 and bz > 0 else float("inf")
        tb.step(f"Abfindung je Beschäftigungsjahr in Monatsgehältern = {fmt_eur(abf)} / ({fmt_eur(monat)} × "
                f"{fmt_num(bz, 1)} Jahre) = " + (fmt_num(ratio, 2) if ratio != float("inf") else "nicht bestimmbar"))
        in_range = lo <= ratio <= hi
        tb.step(f"Spanne für den wichtigen Grund {fmt_num(lo, 2)} bis {fmt_num(hi, 2)} → "
                + ("eingehalten" if in_range else "nicht eingehalten"))
        months = tb.s(f"{base}.kfrist_monate", "Kündigungsfrist Arbeitgeber (Monate)")
        vs = tb.s(f"{base}.vertragsschluss", "Datum Kündigung / Aufhebungsvertrag")
        fristende = notice_end(vs, months, tb)
        frist_ok = ps.end_date >= fristende
        tb.s(f"{base}.end_date", "Ende Arbeitsverhältnis")
        tb.step(f"Ende Arbeitsverhältnis {fmt_date(ps.end_date)} {'≥' if frist_ok else '<'} Ende der Kündigungsfrist "
                f"{fmt_date(fristende)} → Frist {'eingehalten' if frist_ok else 'nicht eingehalten'}")
        weeks = 0 if in_range and frist_ok else w12
        tb.step(("Wichtiger Grund liegt vor → keine Sperrzeit" if weeks == 0 else
                 f"Kein wichtiger Grund nach dieser Prüfung → Regelsperrzeit {w12} Wochen (alg_sperrzeit_arbeitsaufgabe_wochen)"))
        tb.step("Unterstellt wird ein Aufhebungsvertrag, mit dem einer drohenden betriebsbedingten Kündigung zum selben "
                "Zeitpunkt zuvorgekommen wird. Bei einer Kündigung durch den Arbeitgeber ohne eigenes Zutun gibt es keine "
                "Sperrzeit; das bitte als Angabe eintragen. Die Agentur für Arbeit beurteilt den Einzelfall.")
        tb.flag("unsicher")
        _set(s, tracer, path, weeks, tb)
        rs.add(tb.done(weeks))

    path = f"{base}.arbeitsuchend_datum"
    if derives(s, path) and ps.austritt and ps.alg_aktiv:
        tb = tracer.new(f"abl_{ps.id}_arbeitsuchend", f"Arbeitsuchendmeldung {lab}", "Datum", grp)
        tb.rule("R_Sperrzeit")
        tb.s(f"{base}.end_date", "Ende Arbeitsverhältnis")
        tb.s(f"{base}.vertragsschluss", "Datum Kündigung / Aufhebungsvertrag")
        d, text = melde_deadline(ps, tb)
        tb.step(text)
        tb.step(f"Abgeleitet wird der späteste fristgerechte Tag: {fmt_date(d)}. Eine spätere Meldung führt zu einer "
                "Sperrzeit wegen verspäteter Arbeitsuchendmeldung (§ 38 Abs. 1, § 159 Abs. 1 Nr. 7 SGB III).")
        _set(s, tracer, path, d, tb)
        rs.add(tb.done(d))

    path = f"{base}.kv_beitrag_schaetzung"
    if derives(s, path) and s.active("kv") and ps.kv_aktiv:
        tb = tracer.new(f"abl_{ps.id}_kvbeitrag", f"Freiwilliger KV/PV-Beitrag je Monat {lab}", "EUR2", grp)
        tb.rule("R_KV_Freiwillig")
        if ps.kv_status == "privat":
            tb.step("Bei privater Versicherung lässt sich der Beitrag nicht ableiten; verwendet wird der eingetragene Wert.")
            tb.s(path, "Beitrag je Monat")
            rs.add(tb.done(ps.kv_beitrag_schaetzung))
            tracer.derived[path] = (ps.kv_beitrag_schaetzung, tb.t.id)
            return
        first = ps.end_date + timedelta(days=1)
        y = first.year
        cap = ps.capital_for(y)[0]
        rent = max(0.0, ps.rent_for(y)[0])
        sonst = tb.s(f"{base}.kv_sonstige_einnahmen", "Sonstige beitragspflichtige Einnahmen je Monat")
        inc = (cap + rent) / 12 + sonst
        lo = tb.p("kv_mindestbemessung_monat", y)
        hi = tb.p("kv_bbg_monat", y)
        rate, rtxt = kv_rate_voluntary(s, tb, y)
        bem = min(max(inc, lo), hi)
        amount = round(bem * rate, 2)
        tb.step(f"Einnahmen je Monat {y}: Kapitalerträge {fmt_eur(cap)}/12 + Miete {fmt_eur(rent)}/12 + sonstige "
                f"{fmt_eur(sonst)} = {fmt_eur(inc, 2)}")
        tb.step(f"Bemessung zwischen Mindestbemessung {fmt_eur(lo, 2)} und BBG {fmt_eur(hi, 2)}: {fmt_eur(bem, 2)}")
        tb.step(f"Beitragssatz: {rtxt}")
        tb.step(f"Beitrag = {fmt_eur(bem, 2)} × {fmt_pct(rate, 2)} = {fmt_eur(amount, 2)} je Monat (ohne Abfindung)")
        tb.step("Die Rechnung bestimmt den Beitrag je Monat und Jahr selbst, einschließlich eines Abfindungsanteils "
                "(siehe „Eigene KV/PV-Beiträge“). Angezeigt wird der Beitrag im ersten Monat nach dem Austritt.")
        _set(s, tracer, path, amount, tb)
        rs.add(tb.done(amount))
