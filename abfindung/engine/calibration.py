# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Calibration with the latest tax assessment (Steuerbescheid) of the personal data.

1. Tariff check: tariff(zvE from the assessment) vs. assessed income tax.
2. Special expenses: our model of Vorsorgeaufwendungen for that year (employee shares
   KV/PV, RV incl. employer share) vs. the assessed special expenses. The ratio is
   offered as correction factor for the KV/PV part (Option „Vorsorge-Korrekturfaktor“).
"""

from __future__ import annotations

from ..dates import fmt_eur, fmt_pct
from .health import employee_rate
from .income_tax import RV_RATE_IDS, children_under, _for_year
from .tariff import get_tariff


def calibrate(res, s, tracer, rs) -> None:
    b = s.bescheid
    tb = tracer.new("kalibrierung", "Kalibrierung mit dem Steuerbescheid", "EUR", "Kalibrierung")
    tb.rule("R_Fuenftel_Normal", "R_Basisrente")
    if not b:
        tb.step("Kein Steuerbescheid in den persönlichen Daten.")
        rs.add(tb.done(0.0))
        return
    y = b["jahr"]
    po = b["posten"]
    tb.step(f"Steuerbescheid {y}")
    deviation = 0.0
    joint = s.joint
    tariff = get_tariff(tracer.legal, y, 0.0)
    if tariff.fortgeschrieben or tariff.base_year != y:
        tb.flag("fortgeschrieben").step(f"Hinweis: Für {y} liegt kein eigener Tarif vor; verwendet wird {tariff.describe()}.")
    if "zve" in po and "est_tariflich" in po:
        st = tariff.st(po["zve"], joint)
        deviation = st - po["est_tariflich"]
        tb.step(f"Tarif auf zvE {fmt_eur(po['zve'])}: {fmt_eur(st)} vs. Bescheid {fmt_eur(po['est_tariflich'])} → "
                f"Abweichung {fmt_eur(deviation)}")
    if "sonderausgaben" in po:
        kv_an = av = 0.0
        rv_id = tracer.legal.pick(*RV_RATE_IDS)
        rv_satz = tracer.legal.value(rv_id, y) if rv_id else s.options.rv_satz_annahme
        kv_bbg = tracer.p("kv_bbg_monat", y)
        rv_bbg = tracer.p("rv_bbg_monat", y)
        rate = employee_rate(s, tracer, y)
        rv_total = 0.0
        for ps in s.persons:
            g = ps.annual_equiv(y)
            kv_an += min(g / 12, kv_bbg) * 12 * rate
            if ps.rv_pflichtig:
                rv_total += min(g / 12, rv_bbg) * 12 * rv_satz
        hoechst = tracer.p("av_basisrente_hoechstbetrag_je_person", y) * (2 if joint else 1)
        av = max(0.0, min(rv_total, hoechst) * tracer.p("av_basisrente_abzugsanteil", y) - rv_total / 2)
        cost, _ = _for_year(s.childcare, y)
        n14 = children_under(s, y, 14)
        betr = min(tracer.p("kind_betreuung_anteil", y) * cost, tracer.p("kind_betreuung_hoechstbetrag", y) * n14) if n14 else 0.0
        model = kv_an + av + betr
        target_kv = po["sonderausgaben"] - av - betr
        factor = target_kv / kv_an if kv_an > 0 else 1.0
        tb.step(f"Modell Sonderausgaben {y}: KV/PV-AN-Anteile {fmt_eur(kv_an)} + Altersvorsorge {fmt_eur(av)} + "
                f"Kinderbetreuung {fmt_eur(betr)} = {fmt_eur(model)}; Bescheid {fmt_eur(po['sonderausgaben'])}")
        tb.step(f"Vorgeschlagener Korrekturfaktor für KV/PV-Vorsorge: {factor:.3f} "
                f"(übernehmbar unter Optionen → Vorsorge-Korrekturfaktor)")
        res.extra["vorsorge_faktor_vorschlag"] = factor
        if rv_satz == 0:
            tb.flag("unsicher").step("RV-Beitragssatz fehlt – Altersvorsorge-Anteil nicht modelliert.")
    if "festgesetzt" in po:
        tb.step(f"Festgesetzte Steuer gesamt laut Bescheid: {fmt_eur(po['festgesetzt'])} (inkl. Abgeltungsteuer, "
                f"Kindergeld-Hinzurechnung)")
    rs.add(tb.done(deviation))
