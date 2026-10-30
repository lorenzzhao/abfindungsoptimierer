# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Simplified wage tax (Lohnsteuer) — an exchangeable module.

Used for (a) the self-calculated ALG (R_ALG_Hoehe), (b) the withholding on the
severance (R_LSt_Abfindung) and (c) the liquidity plan. It is an approximation of
§ 39b EStG: annual wage minus employee allowance, special-expense lump sum and a
Vorsorgepauschale estimated with the social-contribution share from the settings.
Tax classes V/VI are approximated with the basic tariff (warning flag).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..dates import fmt_eur, fmt_pct
from .tariff import get_tariff


@dataclass
class LstResult:
    lst: float
    soli: float
    kist: float
    base: float
    steps: list[str] = field(default_factory=list)
    approx_class: bool = False

    @property
    def total(self) -> float:
        return self.lst + self.soli + self.kist


def soli_on(tax: float, joint: bool, year: int, src) -> float:
    """R_Soli: 0 up to the exemption limit, then min(rate x tax, mitigation x (tax - limit)).

    ``src`` is a Tracer or trace builder (anything with ``p(id, year)``)."""
    p = src.p
    fg = soli_freigrenze(joint, year, src)
    if tax <= fg:
        return 0.0
    return min(p("soli_satz") * tax, p("soli_milderungssatz") * (tax - fg))


def soli_freigrenze(joint: bool, year: int, src) -> float:
    """Exemption limit; single assessment uses soli_freigrenze_einzeln (else half the joint value)."""
    if joint or not src.legal.has("soli_freigrenze_einzeln"):
        return src.p("soli_freigrenze_zusammen", year) * (1.0 if joint else 0.5)
    return src.p("soli_freigrenze_einzeln", year)


def kist_rate(s, src) -> float:
    """Church tax rate by federal state (kist_satz_by_bw / kist_satz_sonst)."""
    if not s.options.church:
        return 0.0
    if s.options.bundesland.upper() in ("BY", "BW"):
        return src.p("kist_satz_by_bw")
    return src.p("kist_satz_sonst")


def jahres_lst(gross: float, klasse: str, year: int, s, src, freibetrag: float = 0.0,
               explain: bool = False) -> LstResult:
    """Simplified annual wage tax; ``src`` provides ``p(id, year)`` and ``legal``."""
    p = src.p
    tariff = get_tariff(src.legal, year, s.options.tarif_index)
    if gross <= 0:
        return LstResult(0.0, 0.0, 0.0, 0.0, ["kein Arbeitslohn"] if explain else [])
    an_pausch = p("est_arbeitnehmer_pauschbetrag", year)
    sa_pausch = p("est_sonderausgaben_pauschbetrag_zusammen", year) / 2
    rv_cap = 12 * p("rv_bbg_monat", year)
    vorsorge = s.options.sozialabgaben_anteil * min(gross, rv_cap)
    base = max(0.0, gross - an_pausch - sa_pausch - vorsorge - freibetrag)
    joint = klasse == "III"
    lst = float(tariff.st(base, joint))
    approx = klasse in ("V", "VI")
    soli = soli_on(lst, joint, year, src)
    kist = lst * kist_rate(s, src)
    steps = []
    if explain:
        steps = [
            f"Bemessung: Lohn {fmt_eur(gross)} − AN-Pauschbetrag {fmt_eur(an_pausch)} − SA-Pauschbetrag {fmt_eur(sa_pausch)}"
            f" − Vorsorgepauschale {fmt_pct(s.options.sozialabgaben_anteil, 1)} × {fmt_eur(min(gross, rv_cap))}"
            + (f" − Freibetrag {fmt_eur(freibetrag)}" if freibetrag else "") + f" = {fmt_eur(base)}",
            f"Lohnsteuer Klasse {klasse} ({'Splitting' if joint else 'Grundtarif'}): {fmt_eur(lst)}; Soli {fmt_eur(soli, 2)}"
            + (f"; KiSt {fmt_eur(kist, 2)}" if kist else ""),
        ]
        if approx:
            steps.append("Steuerklasse V/VI wird vereinfacht mit dem Grundtarif angenähert.")
    return LstResult(lst, soli, kist, base, steps, approx)
