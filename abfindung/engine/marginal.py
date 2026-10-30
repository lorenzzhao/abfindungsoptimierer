# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Curves for the 'Knick': total tax over zvE and the marginal effect of a deduction
in the severance year (R_Fuenftel_Progressionsvorbehalt)."""

from __future__ import annotations

from dataclasses import dataclass

from .fifth_rule import est_regulaer


@dataclass
class Curves:
    year: int
    zve_now: float
    tax_now: float
    nullgrenze: float
    zve_nullgrenze: float
    zve: list
    tax: list
    tax_regular: list
    deduction: list
    tax_ded: list
    marginal: list
    alg: float = 0.0


def curves(result, span_low: float = 80_000, span_high: float = 40_000, step: float = 1000,
           ded_max: float = 60_000, ded_step: float = 500) -> Curves | None:
    u = result.main_unit_year()
    if u is None:
        return None
    zve0 = u.zve
    ng = max(0.0, u.v + u.pv)
    zs, ts, tr = [], [], []
    d = -span_high
    while d <= span_low:
        z = zve0 - d
        zs.append(z)
        ts.append(u.tax_for(extra_deduction=d))
        reg = est_regulaer(z, u.pv, u.tariff, u.joint, explain=False).est
        tr.append(reg * (1 + u.params["soli_satz"] + u.kist_satz) if z > 0 else 0.0)
        d += step
    ds, td, mg = [], [], []
    x = 0.0
    prev = None
    while x <= ded_max:
        t = u.tax_for(extra_deduction=x)
        ds.append(x)
        td.append(t)
        mg.append(0.0 if prev is None else (prev - t) / ded_step)
        prev = t
        x += ded_step
    if len(mg) > 1:
        mg[0] = mg[1]
    return Curves(u.year, zve0, u.tax_for(0), ng, zve0 - ng, zs, ts, tr, ds, td, mg, u.pv)


KNICK_POINTS = (-50_000, -20_000, -10_000, 0, 10_000, 20_000, 40_000, 80_000, 120_000)


@dataclass
class Knick:
    """Ä8: additional income tax per extra euro of taxable income over the remaining zvE of the severance year."""
    year: int
    ae: float
    alg: float
    v_now: float
    x: list
    lines: dict          # label -> list of % values
    table: dict          # label -> {point: %}
    y_now: float

    @staticmethod
    def zone(x: float, alg: float) -> str:
        if alg <= 0 and x < 0:
            return "unter der Nullgrenze: nur das Fünftel wirkt"
        if x < -alg:
            return "unter der Nullgrenze mit ALG: ca. 25–35 % (nur das Fünftel wirkt)"
        if x < 0:
            return "zwischen −ALG und 0: ca. 75–100 % (ALG wird zuerst verrechnet)"
        return "über 0: bis ca. 160 %, solange das übrige zvE im Grundfreibetrag liegt (5 × Grenzsatz oben − 4 × unten)"


LINE_LABELS = ("ohne Abfindung", "mit Abfindung, ohne ALG", "mit Abfindung und ALG")


def knick(result, lo: float = -60_000, hi: float = 140_000, step: float = 250, width: float = 1000) -> Knick | None:
    """Numerical derivative of the income tax (without Soli and Günstigerprüfung) w.r.t. the remaining zvE,
    sampled every ``step`` €; forward difference over ``width`` € (smooths the euro rounding of the tariff)."""
    u = result.main_unit_year()
    if u is None or u.ae <= 0:
        return None
    from .fifth_rule import est_fuenftel

    def est(v, ae, pv):
        return est_fuenftel(v, ae, pv, u.tariff, u.joint, u.divisor, False).est

    def slope(v, ae, pv):
        return (est(v + width, ae, pv) - est(v, ae, pv)) / width * 100

    if u.pv > 0:
        params = {LINE_LABELS[0]: (0.0, 0.0), LINE_LABELS[1]: (u.ae, 0.0), LINE_LABELS[2]: (u.ae, u.pv)}
    else:  # no ALG in the year: the line "with ALG" would equal the one without
        params = {LINE_LABELS[0]: (0.0, 0.0), "mit Abfindung": (u.ae, 0.0)}
    xs = []
    x = lo
    while x <= hi:
        xs.append(x)
        x += step
    lines = {lab: [slope(v, ae, pv) for v in xs] for lab, (ae, pv) in params.items()}
    table = {lab: {p: slope(p, ae, pv) for p in KNICK_POINTS} for lab, (ae, pv) in params.items()}
    return Knick(u.year, u.ae, u.pv, u.v, xs, lines, table, slope(u.v, u.ae, u.pv))
