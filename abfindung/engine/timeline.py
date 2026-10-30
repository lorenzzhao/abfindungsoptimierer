# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Day-exact timeline per person (output aggregated per month).

Statuses: beschaeftigt | freigestellt | sperrzeit | ruhen_158 | ruhen_157 | alg_bezug |
ohne_leistung | neue_beschaeftigung

Rules: R_Sperrzeit, R_Ruhen158, R_Ruhen157, R_Parallel, R_ALG_Dauer, R_Freistellung.
Sperrzeit and Ruhen run in parallel; ALG starts at
max(registration, end of Sperrzeit + 1, end of Ruhen + 1).
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta

from ..dates import (add_months, add_years, age_on, days_in_month, end_of_month, fmt_date, fmt_eur, fmt_num,
                     fmt_pct, iter_days, months_between)
from .alg import gross_last_months

ONE = timedelta(days=1)

STATUS_LABEL = {
    "beschaeftigt": "Beschäftigt",
    "freigestellt": "Freigestellt",
    "sperrzeit": "Sperrzeit",
    "ruhen_158": "Ruhen § 158",
    "ruhen_157": "Ruhen § 157",
    "alg_bezug": "ALG-Bezug",
    "ohne_leistung": "Ohne Leistung",
    "neue_beschaeftigung": "Neue Beschäftigung",
}


@dataclass
class MonthAgg:
    days: Counter = field(default_factory=Counter)
    alg: float = 0.0
    gross_old: float = 0.0
    gross_new: float = 0.0


@dataclass
class Day:
    status: str
    sperr: bool = False
    r158: bool = False
    r157: bool = False
    alg: float = 0.0


@dataclass
class PersonTimeline:
    pid: str
    end: date
    freistellung_ab: date | None
    fristende: date
    frist_monate: float
    ruhen158: bool
    ruhen158_end: date | None
    ruhen158_anteil: float
    ruhen157_end: date | None
    sperr_start: date | None
    sperr_end: date | None
    melde_start: date | None
    melde_end: date | None
    entstehung: date | None
    alg_start: date | None
    alg_end: date | None = None
    anspruch_tabelle: int = 0
    minderung: int = 0
    anspruch: int = 0
    rest: int = 0
    rate_tag: float = 0.0
    anwartschaft_monate: int = 0
    anwartschaft_ok: bool = True
    vers_monate: int = 0
    alter_entstehung: int = 0
    erloeschen: date | None = None
    minderung_entfaellt: bool = False
    days: dict = field(default_factory=dict)       # date -> Day
    months: dict = field(default_factory=dict)     # (y, m) -> MonthAgg
    warnings: list = field(default_factory=list)   # (text, [rules])

    def alg_in_year(self, year: int) -> float:
        return sum(a.alg for (y, _), a in self.months.items() if y == year)

    def gross_in_year(self, year: int) -> tuple[float, float]:
        old = sum(a.gross_old for (y, _), a in self.months.items() if y == year)
        new = sum(a.gross_new for (y, _), a in self.months.items() if y == year)
        return old, new


def notice_end(vs: date, months: float, tb) -> date:
    """End of the employer's notice period when given notice on ``vs`` (§ 622 BGB)."""
    if months >= 1:
        return end_of_month(add_months(vs, int(round(months))))
    weeks = tb.p("ar_kuendigungsfrist_grund_wochen")
    d = vs + timedelta(days=int(7 * weeks))
    return date(d.year, d.month, 15) if d.day <= 15 else end_of_month(d)


def frist_from_table(bz: float, tb) -> float:
    rows = tb.legal.table("T_Kuendigungsfristen_AG").rows
    best = 0.0
    for r in rows:
        if bz >= r["betriebsjahre_min"]:
            best = max(best, r["frist_monate"])
    return best


def melde_deadline(ps, src) -> tuple:
    """Latest Arbeitsuchendmeldung without a Sperrzeit (§ 38 Abs. 1 SGB III): 3 months before the end of the
    employment, or within a few days of knowledge if the time between contract and end is shorter."""
    frist_m = int(src.p("alg_arbeitsuchend_frist_monate"))
    kurz = int(src.p("alg_arbeitsuchend_kurzfrist_tage"))
    E = ps.end_date
    if add_months(E, -frist_m) >= ps.vertragsschluss:
        d = add_months(E, -frist_m)
        text = (f"Ende Arbeitsverhältnis {fmt_date(E)} − {frist_m} Monate (alg_arbeitsuchend_frist_monate) = {fmt_date(d)}; "
                f"liegt nach dem Vertragsdatum {fmt_date(ps.vertragsschluss)}")
    else:
        d = ps.vertragsschluss + timedelta(days=kurz)
        text = (f"Zwischen Vertragsdatum {fmt_date(ps.vertragsschluss)} und Ende {fmt_date(E)} liegen weniger als {frist_m} "
                f"Monate → Meldung binnen {kurz} Tagen nach Kenntnis (alg_arbeitsuchend_kurzfrist_tage): {fmt_date(d)}")
    return d, text


def anspruch_tabelle(vers_monate: int, alter: int, tb) -> int:
    rows = tb.legal.table("T_ALG_Anspruchsdauer").rows
    best = 0
    for r in rows:
        if vers_monate >= r["versicherungsmonate_min"] and alter >= r["alter_min"]:
            best = max(best, int(r["anspruch_tage"]))
    return best


def build_timeline(ps, idx: int, s, tracer, rs, rate_tag: float, sim_end: date) -> PersonTimeline:
    lab = ps.label
    grp = f"ALG – {lab}"
    base = f"persons.{idx}"
    E = ps.end_date
    F = ps.freistellung_ab if ps.freistellung and ps.freistellung_ab <= E else None
    sim_start = date(s.options.horizon_start, 1, 1)

    # -- notice period / Ruhen § 158 (R_Ruhen158) --------------------------------
    tb = tracer.new(f"tl_{ps.id}_fristende", f"Fiktives Ende der Kündigungsfrist {lab}", "Datum", grp)
    tb.rule("R_Ruhen158")
    months = tb.s(f"{base}.kfrist_monate", "Kündigungsfrist Arbeitgeber (Monate)")
    vs = tb.s(f"{base}.vertragsschluss", "Datum Kündigung / Aufhebungsvertrag")
    fristende = notice_end(vs, months, tb)
    tb.step(f"Fristende = Monatsende nach {fmt_date(vs)} + {fmt_num(months, 0)} Monate = {fmt_date(fristende)}")
    tb.s(f"{base}.end_date", "Ende Arbeitsverhältnis")
    ruhen158 = E < fristende
    tb.step(f"Ende Arbeitsverhältnis {fmt_date(E)} {'<' if ruhen158 else '≥'} Fristende → "
            + ("Frist unterschritten, Ruhen nach § 158 SGB III" if ruhen158 else "Frist eingehalten, kein Ruhen nach § 158"))
    rs.add(tb.done(fristende))

    tb = tracer.new(f"tl_{ps.id}_ruhen158", f"Ruhen § 158 SGB III bis {lab}", "Datum", grp)
    tb.rule("R_Ruhen158").child(f"tl_{ps.id}_fristende")
    r158_end = None
    anteil = 0.0
    if ruhen158:
        start = tb.p("alg_ruhen158_anrechnung_start")
        schritt = tb.p("alg_ruhen158_anrechnung_schritt")
        alter_ab = tb.p("alg_ruhen158_anrechnung_alter_ab")
        amin = tb.p("alg_ruhen158_anrechnung_min")
        maxj = int(tb.p("alg_ruhen158_max_jahre"))
        alter = age_on(ps.birth, E)
        bz = tb.s(f"{base}.bz_jahre", "Betriebszugehörigkeit (Jahre)")
        n_bz = math.floor(bz / 5)
        n_alt = math.floor(max(0, alter - alter_ab) / 5)
        anteil = max(amin, start - schritt * n_bz - schritt * n_alt)
        abf = tb.s(f"{base}.severance", "Abfindung (brutto)")
        brutto12 = gross_last_months(ps, E, 12)
        entgelt_tag = brutto12 / 365 if brutto12 > 0 else 0.0
        tage = math.floor(anteil * abf / entgelt_tag) if entgelt_tag > 0 else 10 ** 6
        e1 = fristende
        e2 = add_years(E, maxj)
        e3 = E + timedelta(days=tage)
        r158_end = min(e1, e2, e3)
        tb.step(f"Anrechenbarer Anteil = max({fmt_pct(amin, 0)}; {fmt_pct(start, 0)} − {fmt_pct(schritt, 0)} × {n_bz} "
                f"(je 5 Jahre Betriebszugehörigkeit) − {fmt_pct(schritt, 0)} × {n_alt} (je 5 Lebensjahre über {fmt_num(alter_ab, 0)}, "
                f"Alter {alter})) = {fmt_pct(anteil, 0)}")
        tb.step(f"Kalendertägliches Arbeitsentgelt = {fmt_eur(brutto12)} / 365 = {fmt_eur(entgelt_tag, 2)}")
        tb.step(f"Verbrauch: {fmt_pct(anteil, 0)} × {fmt_eur(abf)} / {fmt_eur(entgelt_tag, 2)} = {tage} Tage → {fmt_date(e3)}")
        tb.step(f"Ende = min(Fristende {fmt_date(e1)}; Ende AV + {maxj} Jahr {fmt_date(e2)}; Verbrauch {fmt_date(e3)}) = {fmt_date(r158_end)}")
        rs.add(tb.done(r158_end))
    else:
        tb.step("Kein Ruhen: die ordentliche Kündigungsfrist wurde eingehalten.")
        rs.add(tb.done("kein Ruhen"))
        rs[f"tl_{ps.id}_ruhen158"].unit = "Text"

    r157_end = E + timedelta(days=ps.urlaub_tage) if ps.urlaub_tage > 0 else None

    # -- Sperrzeit (R_Sperrzeit) ----------------------------------------------------
    tb = tracer.new(f"tl_{ps.id}_sperrzeit", f"Sperrzeit bis {lab}", "Datum", grp)
    tb.rule("R_Sperrzeit", "R_Parallel")
    weeks = tb.s(f"{base}.sperrzeit_wochen", "Sperrzeit (Wochen)")
    sperr_start = sperr_end = None
    if weeks > 0:
        if F and ps.sperrzeit_ab_freistellung:
            sperr_start = F
            tb.step(f"Beginn mit Beschäftigungslosigkeit = Freistellungsbeginn {fmt_date(F)} (R_Freistellung)")
            tb.rule("R_Freistellung")
        else:
            sperr_start = E + ONE
            tb.step(f"Beginn am Tag nach Ende des Arbeitsverhältnisses: {fmt_date(sperr_start)}")
        sperr_end = sperr_start + timedelta(days=7 * weeks - 1)
        tb.step(f"Dauer {weeks} Wochen = {7 * weeks} Tage → Ende {fmt_date(sperr_end)}; läuft kalendermäßig ab, auch ohne Antrag")
        if weeks == int(tb.p("alg_sperrzeit_arbeitsaufgabe_wochen")):
            tb.step("Regelsperrzeit bei Arbeitsaufgabe (alg_sperrzeit_arbeitsaufgabe_wochen)")
        rs.add(tb.done(sperr_end))
    else:
        tb.step("Keine Sperrzeit angenommen (z. B. wichtiger Grund, R_WichtigerGrund).")
        tb.rule("R_WichtigerGrund")
        rs.add(tb.done("keine"))
        rs[f"tl_{ps.id}_sperrzeit"].unit = "Text"

    meldefrist, _ = melde_deadline(ps, tracer)
    melde_start = melde_end = None
    if ps.arbeitsuchend_datum > meldefrist:
        w = int(tracer.p("alg_sperrzeit_meldeversaeumnis_wochen"))
        melde_start = max((sperr_end + ONE) if sperr_end else E + ONE, E + ONE)
        melde_end = melde_start + timedelta(days=7 * w - 1)
        tracer.used_rules.add("R_Sperrzeit")
        warn = (f"{lab}: Arbeitsuchendmeldung am {fmt_date(ps.arbeitsuchend_datum)} nach Frist {fmt_date(meldefrist)} – "
                f"zusätzliche Sperrzeit {w} Woche(n) bis {fmt_date(melde_end)}.", ["R_Sperrzeit"])
    else:
        warn = None

    # -- entitlement (R_ALG_Dauer) ---------------------------------------------------
    first_unemployed = E + ONE
    entstehung = max(ps.meldung, first_unemployed)
    no_alg_job = ps.newjob and ps.newjob_start <= entstehung
    tb = tracer.new(f"tl_{ps.id}_dauer", f"ALG-Anspruchsdauer {lab}", "Tage", grp)
    tb.rule("R_ALG_Dauer")
    tb.s(f"{base}.meldung", "Arbeitslosmeldung")
    tb.step(f"Anspruchsentstehung = max(Arbeitslosmeldung {fmt_date(ps.meldung)}; erster Tag ohne Beschäftigung "
            f"{fmt_date(first_unemployed)}) = {fmt_date(entstehung)}")
    vb = tb.s(f"{base}.vorbeschaeftigung_monate", "Versicherte Monate vor dem jetzigen Arbeitgeber")
    emp_start = add_months(E, -int(round(ps.bz_jahre * 12)))
    insured_start = add_months(emp_start, -int(vb))
    rahmen = int(tb.p("alg_rahmenfrist_monate"))
    anw_min = int(tb.p("alg_anwartschaft_monate"))
    rahmen_start = add_months(entstehung, -rahmen)
    anw = months_between(max(rahmen_start, insured_start), min(E, entstehung - ONE) + ONE) if E >= rahmen_start else 0
    anw_ok = anw >= anw_min
    tb.step(f"Anwartschaft: {anw} Versicherungsmonate in der Rahmenfrist von {rahmen} Monaten "
            f"(ab {fmt_date(rahmen_start)}), nötig {anw_min} → {'erfüllt' if anw_ok else 'NICHT erfüllt'}")
    if tracer.legal.has("alg_rahmenfrist_erweitert_monate"):
        erw = int(tb.p("alg_rahmenfrist_erweitert_monate"))
    else:
        erw = 60
        tb.flag("unsicher").note("Parameter alg_rahmenfrist_erweitert_monate fehlt; 5 Jahre laut Tabellenhinweis angenommen.")
    vers = months_between(max(add_months(entstehung, -erw), insured_start), E + ONE)
    alter = age_on(ps.birth, entstehung)
    tab = anspruch_tabelle(vers, alter, tb)
    tb.step(f"T_ALG_Anspruchsdauer: {vers} Versicherungsmonate (erweiterte Rahmenfrist {erw} Monate), "
            f"Alter {alter} bei Entstehung → {tab} Tage")
    ereignis = F if (s.options.ein_jahres_ereignis == "freistellung" and F) else E
    entfaellt = s.options.ein_jahres_regel and entstehung > add_years(ereignis, int(tb.p("alg_minderung_entfaellt_nach_jahren")))
    sperr_days = 7 * weeks if weeks > 0 else 0
    if entfaellt:
        minderung = 0
        tb.step(f"Ereignis ({'Freistellungsbeginn' if ereignis == F else 'Ende Beschäftigung'}) {fmt_date(ereignis)} liegt bei "
                f"Anspruchsentstehung mehr als ein Jahr zurück → keine Minderung (§ 148 Abs. 2 Satz 2 SGB III)")
    else:
        minderung = sperr_days
        if weeks == int(tb.p("alg_sperrzeit_arbeitsaufgabe_wochen")) and weeks > 0:
            anteil_min = tb.p("alg_minderung_sperrzeit_mindestanteil")
            minderung = max(sperr_days, math.ceil(anteil_min * tab))
            tb.step(f"Minderung bei {weeks} Wochen Sperrzeit: max({sperr_days} Tage; {fmt_pct(anteil_min, 0)} × {tab}) = {minderung} Tage")
        elif sperr_days:
            tb.step(f"Minderung um die Sperrzeittage: {sperr_days}")
        if not s.options.ein_jahres_regel:
            tb.step("Ein-Jahres-Regel ausgeschaltet (Option „Offene Rechtsfragen“).")
    if melde_end:
        minderung += (melde_end - melde_start).days + 1
        tb.step("Zusätzliche Minderung durch Sperrzeit wegen verspäteter Arbeitsuchendmeldung.")
    anspruch = max(0, tab - minderung) if (anw_ok and not no_alg_job) else 0
    if not anw_ok:
        tb.step("Anwartschaft nicht erfüllt → kein ALG.")
    if no_alg_job and ps.alg_aktiv:
        tb.step("Neue Beschäftigung beginnt vor Anspruchsentstehung → kein ALG.")
    tb.step(f"Anspruchsdauer = {tab} − {minderung} = {anspruch} Tage")
    rs.add(tb.done(anspruch))

    # -- start (R_Parallel) ----------------------------------------------------------
    cands = [entstehung]
    if sperr_end:
        cands.append(sperr_end + ONE)
    if r158_end:
        cands.append(r158_end + ONE)
    if r157_end:
        cands.append(r157_end + ONE)
    if melde_end:
        cands.append(melde_end + ONE)
    alg_start = max(cands) if anspruch > 0 else None
    tb = tracer.new(f"tl_{ps.id}_alg_start", f"ALG-Beginn {lab}", "Datum", grp)
    tb.rule("R_Parallel", "R_Ruhen157").child(f"tl_{ps.id}_sperrzeit", f"tl_{ps.id}_ruhen158", f"tl_{ps.id}_dauer")
    parts = [f"Anspruchsentstehung {fmt_date(entstehung)}"]
    if sperr_end:
        parts.append(f"Ende Sperrzeit + 1 = {fmt_date(sperr_end + ONE)}")
    if r158_end:
        parts.append(f"Ende Ruhen § 158 + 1 = {fmt_date(r158_end + ONE)}")
    if r157_end:
        parts.append(f"Ende Ruhen § 157 (Urlaubsabgeltung) + 1 = {fmt_date(r157_end + ONE)}")
    if melde_end:
        parts.append(f"Ende Meldeversäumnis-Sperrzeit + 1 = {fmt_date(melde_end + ONE)}")
    tb.step("Sperrzeit und Ruhen laufen parallel; ALG-Beginn = max(" + "; ".join(parts) + ")")
    tb.step(f"→ {fmt_date(alg_start) if alg_start else 'kein ALG'}")
    rs.add(tb.done(alg_start if alg_start else "kein ALG"))
    if not alg_start:
        rs[f"tl_{ps.id}_alg_start"].unit = "Text"

    tl = PersonTimeline(
        pid=ps.id, end=E, freistellung_ab=F, fristende=fristende, frist_monate=months, ruhen158=ruhen158,
        ruhen158_end=r158_end, ruhen158_anteil=anteil, ruhen157_end=r157_end, sperr_start=sperr_start,
        sperr_end=sperr_end, melde_start=melde_start, melde_end=melde_end, entstehung=entstehung,
        alg_start=alg_start, anspruch_tabelle=tab, minderung=minderung, anspruch=anspruch, rate_tag=rate_tag,
        anwartschaft_monate=anw, anwartschaft_ok=anw_ok, vers_monate=vers, alter_entstehung=alter,
        erloeschen=add_years(entstehung, int(tracer.p("alg_erloeschen_jahre"))), minderung_entfaellt=entfaellt,
    )
    if warn:
        tl.warnings.append(warn)
    if no_alg_job:
        tl.warnings.append((f"{lab}: Die neue Beschäftigung beginnt am {fmt_date(ps.newjob_start)} vor der geplanten "
                            f"Arbeitslosmeldung ({fmt_date(ps.meldung)}) – aus dieser Meldung entsteht kein ALG "
                            f"(eine Meldung nach mehr als einem Jahr ist dann nicht möglich).", ["R_ALG_Dauer"]))
    if not anw_ok and ps.alg_aktiv:
        tl.warnings.append((f"{lab}: Anwartschaftszeit nicht erfüllt ({anw} von {anw_min} Monaten) – kein ALG.", ["R_ALG_Dauer"]))
    if ruhen158 and ps.alg_aktiv:
        tl.warnings.append((f"{lab}: Kündigungsfrist unterschritten – ALG ruht bis {fmt_date(r158_end)}; "
                            f"keine KV über die Agentur in dieser Zeit.", ["R_Ruhen158", "R_KV_RuhenAbfindung"]))

    # -- day loop --------------------------------------------------------------------
    remaining = anspruch
    last_paid = None
    sal_cache: dict[int, float] = {}
    for d in iter_days(sim_start, sim_end):
        m = tl.months.setdefault((d.year, d.month), MonthAgg())
        sperr = bool(sperr_start and sperr_start <= d <= sperr_end) or bool(melde_start and melde_start <= d <= melde_end)
        r158 = bool(r158_end and E < d <= r158_end)
        r157 = bool(r157_end and E < d <= r157_end)
        if d <= E:
            st = "freigestellt" if F and d >= F else "beschaeftigt"
        elif ps.newjob and d >= ps.newjob_start:
            st = "neue_beschaeftigung"
        elif alg_start and d >= alg_start and remaining > 0 and d < tl.erloeschen:
            st = "alg_bezug"
        elif sperr:
            st = "sperrzeit"
        elif r158:
            st = "ruhen_158"
        elif r157:
            st = "ruhen_157"
        else:
            st = "ohne_leistung"
        day = Day(st, sperr, r158, r157)
        if st == "alg_bezug":
            # A calendar month counts as 30 days (alg_tage_pro_monat).
            if d.day != 31:
                n = 1
                dim = days_in_month(d.year, d.month)
                if d.month == 2 and d.day == dim and alg_start <= d.replace(day=1):
                    n += 30 - dim
                n = min(n, remaining)
                remaining -= n
                day.alg = n * rate_tag
                last_paid = d
        tl.days[d] = day
        m.days[st] += 1
        m.alg += day.alg
        dim = days_in_month(d.year, d.month)
        if st in ("beschaeftigt", "freigestellt"):
            if d.year not in sal_cache:
                sal_cache[d.year] = ps.annual_equiv(d.year)
            m.gross_old += sal_cache[d.year] / 12 / dim
        elif st == "neue_beschaeftigung":
            m.gross_new += ps.newjob_salary / 12 / dim
    tl.alg_end = last_paid
    tl.rest = remaining
    if remaining > 0 and anspruch > 0:
        if ps.newjob:
            tl.warnings.append((f"{lab}: Restanspruch {remaining} Tage (neue Beschäftigung); erlischt am "
                                f"{fmt_date(tl.erloeschen)}.", ["R_ALG_Dauer"]))
    return tl


def alg_traces(tl: PersonTimeline, ps, s, tracer, rs) -> None:
    lab = ps.label
    grp = f"ALG – {lab}"
    years = s.years()
    for y in years:
        tb = tracer.new(f"alg_{ps.id}_{y}", f"ALG {y} {lab}", "EUR", grp)
        tb.rule("R_ALG_Hoehe", "R_ALG_Steuer").child(f"alg_{ps.id}_rate", f"tl_{ps.id}_alg_start", f"tl_{ps.id}_dauer")
        days = sum(a.days["alg_bezug"] for (yy, _), a in tl.months.items() if yy == y)
        val = tl.alg_in_year(y)
        tb.step(f"{days} Kalendertage im ALG-Bezug in {y} (Monat = 30 Tage) × Tagessatz {fmt_eur(tl.rate_tag, 2)} = {fmt_eur(val, 2)}")
        tb.step("ALG ist steuerfrei, unterliegt aber dem Progressionsvorbehalt (§ 32b EStG).")
        rs.add(tb.done(val))
    tb = tracer.new(f"alg_{ps.id}_total", f"ALG im Horizont {lab}", "EUR", grp)
    tb.child(*[f"alg_{ps.id}_{y}" for y in years], f"alg_{ps.id}_rate", f"tl_{ps.id}_alg_start", f"tl_{ps.id}_dauer")
    tb.rule("R_ALG_Hoehe", "R_ALG_Dauer")
    tot = sum(tl.alg_in_year(y) for y in years)
    allv = sum(a.alg for a in tl.months.values())
    tb.step(" + ".join(f"{y}: {fmt_eur(tl.alg_in_year(y))}" for y in years) + f" = {fmt_eur(tot)}")
    if tl.alg_start:
        tb.step(f"Bezug {fmt_date(tl.alg_start)} bis {fmt_date(tl.alg_end)}; Anspruch {tl.anspruch} Tage, Rest {tl.rest} Tage")
    if allv - tot > 1:
        tb.step(f"Außerhalb des Horizonts zusätzlich {fmt_eur(allv - tot)} (nicht im Saldo).")
    rs.add(tb.done(tot))
