# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Fünftelregelung (§ 34 Abs. 1 EStG) combined with Progressionsvorbehalt (§ 32b EStG).

R_Fuenftel_Progressionsvorbehalt (BFH VI R 44/07, IX R 93/07), implemented exactly:

    v  = remaining zvE (zvE without extraordinary income, may be negative)
    AE = extraordinary income (severance in the year)
    PV = income subject to Progressionsvorbehalt (ALG of the year)
    satz(x) = St(x)/x, 0 if x <= 0

    AE == 0:  ESt = v > 0 ? v * satz(v + PV) : 0
    v >= 0:   rest = v * satz(v + PV)
              diff = (v + AE/5) * satz(v + AE/5 + PV) - rest
              ESt  = rest + 5 * diff
    v < 0:    zvE = v + AE; zvE <= 0 -> ESt = 0
              R = max(0, v + PV)       # ALG is first offset against negative v
              f = zvE / 5
              ESt = 5 * f * satz(f + R)
"""

from __future__ import annotations

import math

_EPS = 1e-6  # guard against float error before rounding down
from dataclasses import dataclass, field

from ..dates import fmt_eur, fmt_pct


@dataclass
class FifthResult:
    est: int
    case: str
    steps: list[str] = field(default_factory=list)


def est_fuenftel(v: float, ae: float, pv: float, tariff, joint: bool, divisor: int = 5,
                 explain: bool = True) -> FifthResult:
    """R_Fuenftel_Progressionsvorbehalt; v and AE are rounded down to full euros (§ 32a Abs. 1)."""
    v = math.floor(v)
    ae = max(0, math.floor(ae))
    pv = max(0.0, pv)
    d = divisor

    def satz(x):
        return tariff.rate(x, joint)

    steps: list[str] = []
    if ae <= 0:
        if v <= 0:
            return FifthResult(0, "kein_zvE", ["zvE ≤ 0 → ESt = 0"] if explain else [])
        s = satz(v + pv)
        est = v * s
        if explain:
            if pv > 0:
                steps.append(f"Progressionsvorbehalt: satz(v + PV) = St({fmt_eur(v + pv)}) / {fmt_eur(v + pv)} = {fmt_pct(s, 4)}")
                steps.append(f"ESt = v × satz = {fmt_eur(v)} × {fmt_pct(s, 4)} = {fmt_eur(est, 2)}")
            else:
                steps.append(f"ESt = St({fmt_eur(v)}) = {fmt_eur(est, 2)}")
        return FifthResult(math.floor(est + _EPS), "regulaer", steps)

    if v >= 0:
        s1 = satz(v + pv)
        rest = v * s1
        x2 = v + ae / d
        s2 = satz(x2 + pv)
        diff = x2 * s2 - rest
        est = rest + d * diff
        if explain:
            steps += [
                f"Fall v ≥ 0 (v = {fmt_eur(v)}, AE = {fmt_eur(ae)}, PV = {fmt_eur(pv)})",
                f"rest = v × satz(v + PV) = {fmt_eur(v)} × {fmt_pct(s1, 4)} = {fmt_eur(rest, 2)}",
                f"v + AE/{d} = {fmt_eur(x2, 2)}; satz(v + AE/{d} + PV) = {fmt_pct(s2, 4)}",
                f"diff = {fmt_eur(x2, 2)} × {fmt_pct(s2, 4)} − rest = {fmt_eur(diff, 2)}",
                f"ESt = rest + {d} × diff = {fmt_eur(rest, 2)} + {d} × {fmt_eur(diff, 2)} = {fmt_eur(est, 2)}",
            ]
        return FifthResult(math.floor(est + _EPS), "v_positiv", steps)

    zve = v + ae
    if zve <= 0:
        return FifthResult(0, "zvE_negativ", [f"zvE = v + AE = {fmt_eur(zve)} ≤ 0 → ESt = 0"] if explain else [])
    r = max(0.0, v + pv)
    f = zve / d
    s = satz(f + r)
    est = d * f * s
    if explain:
        steps += [
            f"Fall v < 0 (v = {fmt_eur(v)}, AE = {fmt_eur(ae)}, PV = {fmt_eur(pv)})",
            f"zvE = v + AE = {fmt_eur(zve)}",
            f"R = max(0, v + PV) = {fmt_eur(r)} (ALG wird zuerst mit dem negativen v verrechnet)",
            f"f = zvE / {d} = {fmt_eur(f, 2)}; satz(f + R) = {fmt_pct(s, 4)}",
            f"ESt = {d} × f × satz(f + R) = {fmt_eur(est, 2)}",
        ]
    return FifthResult(math.floor(est + _EPS), "v_negativ", steps)


def est_regulaer(zve: float, pv: float, tariff, joint: bool, explain: bool = True) -> FifthResult:
    """Without Fünftelregelung: R_Progressionsvorbehalt, ESt = zvE * St(zvE + PV) / (zvE + PV)."""
    zve = math.floor(zve)
    if zve <= 0:
        return FifthResult(0, "kein_zvE", ["zvE ≤ 0 → ESt = 0"] if explain else [])
    s = tariff.rate(zve + max(0.0, pv), joint)
    est = zve * s
    steps = [f"ESt = zvE × satz(zvE + PV) = {fmt_eur(zve)} × {fmt_pct(s, 4)} = {fmt_eur(est, 2)}"] if explain else []
    return FifthResult(math.floor(est + _EPS), "regulaer", steps)
