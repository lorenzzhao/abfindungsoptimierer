# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Amount of unemployment benefit ALG I (R_ALG_Hoehe, §§ 149–154 SGB III).

Origin "angabe"/"annahme": the monthly amount from the personal XML (adjustable by slider).
Origin "abgeleitet": own calculation from the gross wage of the assessment period:
  BE_Tag = min(gross of the last ``alg_bemessungsrahmen_monate`` months, BBG) / 365
  Leistungsentgelt = BE_Tag − SV-Pauschale − LSt − Soli (simplified wage tax)
  ALG_Tag = Leistungsentgelt × Leistungssatz (with / without child)
The severance does not reduce the ALG; it only acts via R_Ruhen158.
"""

from __future__ import annotations

from ..dates import add_months, fmt_eur, fmt_pct
from .payroll import jahres_lst


def has_child(s) -> bool:
    return any(kg for _, kg in s.children)


def gross_last_months(ps, end, months: int, cap_month: float | None = None) -> float:
    """Gross wage of the ``months`` calendar months ending with the month of ``end``."""
    total = 0.0
    d = end.replace(day=1)
    for i in range(months):
        m = add_months(d, -i)
        sal = ps.annual_equiv(m.year)
        val = sal / 12
        if cap_month is not None:
            val = min(val, cap_month)
        total += val
    return total


def alg_rate(ps, idx: int, s, tracer):
    """Returns (Traced monthly amount, daily rate)."""
    label = ps.label
    tb = tracer.new(f"alg_{ps.id}_rate", f"ALG-Monatsbetrag {label}", "EUR2", f"ALG – {label}")
    tb.rule("R_ALG_Hoehe")
    if not (ps.austritt and ps.alg_aktiv):
        tb.step("Kein Arbeitslosengeld: " + ("kein Austritt." if not ps.austritt else "nicht beantragt (Schalter "
                                             "„Arbeitslosengeld beantragen“)."))
        return tb.done(0.0), 0.0
    tage = tb.p("alg_tage_pro_monat")
    year = ps.end_date.year
    path = f"persons.{idx}.alg_monat"
    if s.origin_of(path) == "abgeleitet":
        months = int(tb.p("alg_bemessungsrahmen_monate"))
        bbg = tb.p("alg_bbg_monat", year)
        brutto = gross_last_months(ps, ps.end_date, months, bbg)
        be_tag = brutto / 365
        sv = tb.p("alg_sv_pauschale")
        lst = jahres_lst(be_tag * 365, ps.steuerklasse, year, s, tb, explain=True)
        lst_tag = (lst.lst + lst.soli) / 365
        le = be_tag * (1 - sv) - lst_tag
        satz = tb.p("alg_satz_mit_kind") if has_child(s) else tb.p("alg_satz_ohne_kind")
        tag = max(0.0, le * satz)
        monat = tag * tage
        tb.s(f"persons.{idx}.salary.{year}", f"Bruttogehalt {year}")
        tb.step(f"Bemessungsentgelt: Brutto der letzten {months} Monate bis {ps.end_date:%m/%Y}, je Monat max. "
                f"{fmt_eur(bbg)} (alg_bbg_monat) = {fmt_eur(brutto)} → je Tag {fmt_eur(be_tag, 2)}")
        tb.step(f"SV-Pauschale {fmt_pct(sv, 0)}: {fmt_eur(be_tag * sv, 2)} je Tag")
        for st in lst.steps:
            tb.step("Lohnsteuer (vereinfacht, auf das Jahres-Bemessungsentgelt): " + st)
        tb.step(f"Leistungsentgelt = {fmt_eur(be_tag, 2)} − {fmt_eur(be_tag * sv, 2)} − {fmt_eur(lst_tag, 2)} = {fmt_eur(le, 2)} je Tag")
        tb.step(f"Leistungssatz {fmt_pct(satz, 0)} ({'mit' if has_child(s) else 'ohne'} Kind) → ALG {fmt_eur(tag, 2)} je Tag")
        tb.step(f"Monatsbetrag = Tagessatz × {tage} = {fmt_eur(monat, 2)}")
        if lst.approx_class:
            tb.flag("unsicher").note("Steuerklasse V/VI vereinfacht.")
        monat = round(monat, 2)
        tb.tr.derived[path] = (monat, tb.t.id)
    else:
        monat = tb.s(path, "ALG-Monatsbetrag (persönliche Daten)")
        tag = monat / tage
        tb.step(f"Monatsbetrag laut persönlichen Daten (per Regler änderbar): {fmt_eur(monat, 2)}")
        tb.step(f"Tagessatz = Monat / {tage} (alg_tage_pro_monat) = {fmt_eur(tag, 2)}")
        tb.flag("unsicher")
    tb.step("Die Abfindung mindert das ALG nicht; sie wirkt nur über das Ruhen nach § 158 SGB III.")
    return tb.done(monat), tag
