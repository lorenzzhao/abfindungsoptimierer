# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Monthly liquidity plan incl. wage tax withholding on the severance.

R_LSt_Abfindung: since 2025 the severance is taxed as an ordinary "sonstiger Bezug"
without Fünftelregelung in the wage tax deduction (parameter lst_fuenftel_im_abzug);
the reduction only comes with the assessment (refund in the assumed notice month).
R_LSt_Ermaessigung: an allowance (Freibetrag) can be entered if applied for in time;
only certain items qualify (not Fünftelregelung, not Vorsorge, not losses of a newly
acquired building).
"""

from __future__ import annotations

from datetime import date

from ..dates import fmt_date, fmt_eur, fmt_month, month_index
from .income_tax import amount_for, children_under, _for_year
from .settings import gestaltungen
from .payroll import jahres_lst


def _freibetrag(s, tracer, rs, ctx) -> tuple[int, float]:
    o = s.options
    y = o.lst_freibetrag_year
    tb = tracer.new("lst_freibetrag", f"Lohnsteuer-Freibetrag {y}", "EUR", "Liquidität")
    tb.rule("R_LSt_Ermaessigung")
    req = tb.s("options.lst_freibetrag", "Beantragter Freibetrag")
    if req <= 0:
        tb.step("Kein Freibetrag beantragt.")
        rs.add(tb.done(0.0))
        return y, 0.0
    bm, bd = tb.p("lst_erm_frist_beginn")
    em, ed = tb.p("lst_erm_frist_ende")
    grenze = tb.p("lst_erm_antragsgrenze")
    antrag = tb.s("options.lst_antrag_datum", "Antragsdatum")
    start, end = date(y - 1, bm, bd), date(y, em, ed)
    valid = start <= antrag <= end
    tb.step(f"Antragsfrist {fmt_date(start)} bis {fmt_date(end)}: Antrag am {fmt_date(antrag)} → "
            + ("fristgerecht" if valid else "außerhalb der Frist"))
    cost, _ = _for_year(s.childcare, y)
    betr = 0.0
    n14 = children_under(s, y, 14)
    if cost and n14:
        betr = min(tracer.p("kind_betreuung_anteil", y) * cost, tracer.p("kind_betreuung_hoechstbetrag", y) * n14)
    rent = sum(ps.rent_for(y)[0] for ps in s.persons) - amount_for(s, "erhaltung", y)
    verlust = max(0.0, -rent)
    eintragbar = betr + verlust
    tb.step(f"Eintragbar: Kinderbetreuung {fmt_eur(betr)} + Verluste aus Vermietung bestehender Objekte {fmt_eur(verlust)} "
            f"= {fmt_eur(eintragbar)} (nicht: Fünftelregelung, Vorsorgeaufwendungen, Verluste eines neu angeschafften Gebäudes)")
    eff = min(req, eintragbar) if valid else 0.0
    if eintragbar < grenze:
        eff = 0.0
        tb.step(f"Antragsgrenze {fmt_eur(grenze)} nicht erreicht.")
    if not valid:
        ctx.warn(f"Lohnsteuer-Freibetrag {y}: Antrag am {fmt_date(antrag)} außerhalb der Frist.", ["R_LSt_Ermaessigung"])
    if req > eintragbar:
        ctx.warn(f"Lohnsteuer-Freibetrag {y}: beantragt {fmt_eur(req)}, eintragbar nur {fmt_eur(eintragbar)}.",
                 ["R_LSt_Ermaessigung"])
    tb.step(f"Wirksamer Freibetrag = {fmt_eur(eff)}")
    rs.add(tb.done(eff))
    return y, eff


def build_liquidity(res, s, tracer, rs, ctx) -> None:
    years = res.years
    fb_year, fb = _freibetrag(s, tracer, rs, ctx)
    rv_bbg = {y: tracer.p("rv_bbg_monat", y) for y in years}
    fuenftel_lst = bool(tracer.legal.value("lst_fuenftel_im_abzug", years[0])) if tracer.legal.has("lst_fuenftel_im_abzug") else False
    months = {(y, m): {"gehalt": 0.0, "abfindung": 0.0, "alg": 0.0, "kv": 0.0, "gestaltung": 0.0, "steuer": 0.0}
              for y in years for m in range(1, 13)}
    withheld: dict[int, float] = {}  # wage tax withheld per year (household)
    cache: dict = {}

    def lst_month(gross_m: float, klasse: str, y: int, fbm: float) -> float:
        k = (round(gross_m, 0), klasse, y, round(fbm))
        if k not in cache:
            cache[k] = jahres_lst(12 * gross_m, klasse, y, s, tracer, freibetrag=12 * fbm).total / 12
        return cache[k]

    for idx, ps in enumerate(s.persons):
        tl = ctx.timelines[ps.id]
        for (y, mth), agg in tl.months.items():
            if y not in years:
                continue
            g = agg.gross_old + agg.gross_new
            fbm = fb / 12 if y == fb_year else 0.0
            if g > 0:
                lst = lst_month(g, ps.steuerklasse, y, fbm)
                months[(y, mth)]["gehalt"] += g - lst - s.options.sozialabgaben_anteil * min(g, rv_bbg[y])
                withheld[y] = withheld.get(y, 0.0) + lst
            months[(y, mth)]["alg"] += agg.alg
        if ps.bonus and ps.bonus_year in years:
            g_old, g_new = tl.gross_in_year(ps.bonus_year)
            j = g_old + g_new
            d = (jahres_lst(j + ps.bonus, ps.steuerklasse, ps.bonus_year, s, tracer).total
                 - jahres_lst(j, ps.steuerklasse, ps.bonus_year, s, tracer).total)
            months[(ps.bonus_year, 12)]["gehalt"] += ps.bonus * (1 - s.options.sozialabgaben_anteil) - d
            withheld[ps.bonus_year] = withheld.get(ps.bonus_year, 0.0) + d
        kv = ctx.kv[ps.id]
        for (y, mth), km in kv.months.items():
            if (y, mth) in months:
                months[(y, mth)]["kv"] -= km.own

        # severance withholding per payment (R_LSt_Abfindung)
        tb = tracer.new(f"lst_abf_{ps.id}", f"Lohnsteuerabzug auf die Abfindung {ps.label}", "EUR", "Liquidität")
        tb.rule("R_LSt_Abfindung")
        if tracer.legal.has("lst_fuenftel_im_abzug"):
            tb.p("lst_fuenftel_im_abzug", years[0])
        total_lst = 0.0
        for mi, amount in ctx.payments[ps.id]:
            y, mth = mi // 12, mi % 12 + 1
            net_amount = amount
            g_old, g_new = tl.gross_in_year(y)
            j = g_old + g_new
            fbj = fb if y == fb_year else 0.0
            base = jahres_lst(j, ps.steuerklasse, y, s, tracer, freibetrag=fbj)
            if fuenftel_lst:
                plus = jahres_lst(j + net_amount / 5, ps.steuerklasse, y, s, tracer, freibetrag=fbj)
                d = 5 * (plus.total - base.total)
            else:
                plus = jahres_lst(j + net_amount, ps.steuerklasse, y, s, tracer, freibetrag=fbj)
                d = plus.total - base.total
            total_lst += d
            tb.step(f"Zahlung {fmt_month(y, mth)}: {fmt_eur(amount)}"
                    + f"; Jahresarbeitslohn {y} {fmt_eur(j)}; LSt+Soli+KiSt(J + Abfindung) − (J) = "
                    f"{fmt_eur(plus.total)} − {fmt_eur(base.total)} = {fmt_eur(d)}"
                    + (" (Fünftelregelung im Abzug)" if fuenftel_lst else " (ohne Fünftelregelung)"))
            if y in years:
                months[(y, mth)]["abfindung"] += net_amount - d
                withheld[y] = withheld.get(y, 0.0) + d
        tb.step("Die Steuerermäßigung nach § 34 EStG wirkt erst mit dem Steuerbescheid (Erstattung).")
        rs.add(tb.done(total_lst))

    # measures (cash)
    for _, g in gestaltungen(s):
        if g.typ != "kauf":
            if g.betrag and (g.jahr, g.monat) in months:
                months[(g.jahr, g.monat)]["gestaltung"] -= g.betrag
            continue
        if g.kaufpreis <= 0:
            continue
        start = month_index(g.jahr, g.monat)
        disagio = g.darlehen * g.disagio_anteil
        equity = g.kaufpreis * (1 + g.nebenkosten_anteil) - (g.darlehen - disagio)
        for (y, mth) in months:
            mi = month_index(y, mth)
            if mi >= start:
                months[(y, mth)]["gestaltung"] += (g.miete_jahr - g.bewirtschaftung_jahr - g.darlehen * g.zins) / 12
            if mi == start:
                months[(y, mth)]["gestaltung"] -= equity

    # tax settlement after assessment
    bm = s.options.bescheid_monat
    for y in res.years:
        w = withheld.get(y, 0.0)
        total = res.tax_by_year[y]
        diff = w - total
        tb = tracer.new(f"erstattung_{y}", f"Erstattung (+) / Nachzahlung (−) für {y}", "EUR", "Liquidität")
        tb.rule("R_LSt_Abfindung").child(f"steuer_{y}", *[f"lst_abf_{ps.id}" for ps in s.persons])
        tb.s("options.bescheid_monat", "Monat des Steuerbescheids im Folgejahr")
        tb.step(f"Einbehaltene Lohnsteuer inkl. Soli/KiSt {fmt_eur(w)} − festgesetzte Steuer {fmt_eur(total)} = {fmt_eur(diff)}")
        tb.step(f"Zahlungswirksam im {fmt_month(y + 1, bm)}" + ("" if (y + 1, bm) in months else " (außerhalb des Horizonts)"))
        tb.step("Vereinfachung: keine Einkommensteuer-Vorauszahlungen, Kapitalertragsteuer an der Quelle abgegolten.")
        rs.add(tb.done(diff))
        if (y + 1, bm) in months:
            months[(y + 1, bm)]["steuer"] += diff

    cum = 0.0
    rows = []
    min_v, min_m = 0.0, None
    for (y, mth) in sorted(months):
        r = months[(y, mth)]
        tot = sum(r.values())
        cum += tot
        rows.append({"jahr": y, "monat": mth, **r, "summe": tot, "kumuliert": cum})
        if cum < min_v or min_m is None:
            min_v, min_m = cum, (y, mth)
    res.liquidity = rows
    res.liq_min, res.liq_min_month = min_v, min_m
    tb = tracer.new("liq_min", "Liquiditätstiefpunkt (kumuliert)", "EUR", "Liquidität")
    tb.rule("R_LSt_Abfindung", "R_LSt_Ermaessigung").child(*[f"lst_abf_{ps.id}" for ps in s.persons], "lst_freibetrag")
    tb.step("Monatliche Zuflüsse: Nettogehalt, Abfindung nach Lohnsteuerabzug, ALG; Abflüsse: eigene KV/PV, "
            "Gestaltungen (inkl. Eigenkapital eines Immobilienkaufs), Steuer-Erstattung/-Nachzahlung im Bescheidmonat.")
    if min_m:
        tb.step(f"Tiefster kumulierter Stand {fmt_eur(min_v)} im {fmt_month(*min_m)} (Start = 0 € am {fmt_month(years[0], 1)}).")
    rs.add(tb.done(min_v))
