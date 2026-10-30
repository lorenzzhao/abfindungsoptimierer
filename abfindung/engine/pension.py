# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Statutory pension insurance — information only, not an optimisation target.

Contribution months and contribution base: employment (incl. Freistellung) up to the
RV assessment ceiling; ALG with ``rv_alg_bemessung_anteil`` of the assessment wage
(R_Rente_ALG); everything else is a gap. Entgeltpunkte only if the legal XML provides
``rv_durchschnittsentgelt`` (average wage of the year).
"""

from __future__ import annotations

from ..dates import fmt_eur, fmt_pct
from .alg import gross_last_months


def pension_traces(res, s, tracer, rs, ctx) -> None:
    years = res.years
    for idx, ps in enumerate(s.persons):
        tl = ctx.timelines[ps.id]
        tb = tracer.new(f"rv_{ps.id}", f"Rentenversicherung (Ausweis) {ps.label}", "EUR", "Rente")
        tb.rule("R_Rente_ALG", "R_Freistellung")
        anteil = tb.p("rv_alg_bemessung_anteil")
        be_month = gross_last_months(ps, tl.end, int(tracer.p("alg_bemessungsrahmen_monate")),
                                     tracer.p("alg_bbg_monat", tl.end.year)) / 12
        total = 0.0
        ep_total = 0.0
        has_avg = tracer.legal.has("rv_durchschnittsentgelt")
        for y in years:
            bbg = tb.p("rv_bbg_monat", y)
            emp_m = alg_m = gap_m = 0.0
            base = 0.0
            for (yy, mm), agg in tl.months.items():
                if yy != y:
                    continue
                dim = sum(agg.days.values())
                emp_days = agg.days["beschaeftigt"] + agg.days["freigestellt"] + agg.days["neue_beschaeftigung"]
                alg_days = agg.days["alg_bezug"]
                if ps.rv_pflichtig and emp_days:
                    base += min(agg.gross_old + agg.gross_new, bbg * emp_days / dim)
                    emp_m += emp_days / dim
                if alg_days:
                    base += anteil * be_month * alg_days / dim
                    alg_m += alg_days / dim
                gap_m += (dim - emp_days - alg_days) / dim if dim else 0
            total += base
            line = (f"{y}: Beschäftigung {emp_m:.1f} Mon., ALG {alg_m:.1f} Mon. ({fmt_pct(anteil, 0)} des Bemessungsentgelts "
                    f"{fmt_eur(be_month)}), Lücke {gap_m:.1f} Mon.; beitragspflichtige Einnahmen {fmt_eur(base)}")
            if has_avg:
                avg = tb.p("rv_durchschnittsentgelt", y)
                ep = base / avg if avg else 0.0
                ep_total += ep
                line += f" → {ep:.3f} Entgeltpunkte"
            tb.step(line)
        if not has_avg:
            tb.step("Entgeltpunkte: Parameter „rv_durchschnittsentgelt“ fehlt in den rechtlichen Vorgaben; nur Bemessungsgrundlage.")
        else:
            tb.step(f"Summe Entgeltpunkte im Horizont: {ep_total:.3f}")
        tb.step("Nur Information; keine Optimierungsgröße.")
        rs.add(tb.done(total))
