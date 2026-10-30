# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Lorenz Zhao
"""Health and long-term care insurance (KV/PV), per day, aggregated per month and person.

Regime per day (R_KV_ALG, R_KV_RuhenAbfindung, R_KV_Familie, R_KV_Freiwillig):
  an          employed or released (Freistellung): employee share of the contribution
  agentur     ALG, Sperrzeit from month ``kv_sperrzeit_agentur_ab_monat`` (if registered),
              Ruhen § 157: paid by the employment agency
  nachgehend  first ``kv_nachgehender_anspruch_monate`` month(s) after compulsory insurance
  freiwillig  own voluntary contribution (also during Ruhen § 158 after the follow-up claim)
  familie     family insurance if income <= threshold
  privat      own private premium (estimate from the personal data)
Severance for voluntarily insured: 1 = not assessed, 2 = assigned to the notice period,
3 = spread over ``kv_abfindung_verteilung_monate`` months from receipt (R_KV_Freiwillig).
For compulsorily insured employees the severance is contribution-free (R_KV_AbfindungPflicht).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import timedelta

from ..dates import add_months, days_in_month, fmt_eur, fmt_month, fmt_pct, month_index, months_between

ONE = timedelta(days=1)

REGIME_LABEL = {
    "an": "Arbeitnehmeranteil",
    "agentur": "Beitrag durch Agentur für Arbeit",
    "nachgehend": "nachgehender Leistungsanspruch",
    "freiwillig": "freiwilliger Beitrag",
    "familie": "Familienversicherung",
    "privat": "private KV (Schätzung)",
}


@dataclass
class KvMonth:
    own: float = 0.0
    an: float = 0.0
    days: Counter = field(default_factory=Counter)
    base: float = 0.0  # assessment base for voluntary contributions


@dataclass
class KvResult:
    months: dict = field(default_factory=dict)
    vol: dict = field(default_factory=dict)        # (y, m) -> (income without severance, lo, hi, rate, mode)
    severance_extra: dict = field(default_factory=dict)  # year -> extra contribution caused by the severance

    def own_year(self, y: int) -> float:
        return sum(m.own for (yy, _), m in self.months.items() if yy == y)

    def an_year(self, y: int) -> float:
        return sum(m.an for (yy, _), m in self.months.items() if yy == y)


def n_children_under(s, year: int, age: int) -> int:
    return sum(1 for gj, _ in s.children if year - gj < age)


def pv_rates(s, src, year: int) -> tuple[float, float, str]:
    """(full PV rate, employee PV rate, explanation) incl. child discount / childless surcharge."""
    basis = src.p("pv_satz_basis", year)
    n = n_children_under(s, year, 25)
    if n == 0:
        z = src.p("pv_kinderlosenzuschlag")
        return basis + z, basis / 2 + z, f"PV {fmt_pct(basis, 2)} + Kinderlosenzuschlag {fmt_pct(z, 2)}"
    rows = src.legal.table("T_PV_Kinderabschlag").rows
    ab = 0.0
    for r in rows:
        if n >= r["kinder"]:
            ab = max(ab, r["abschlag"])
    return basis - ab, basis / 2 - ab, f"PV {fmt_pct(basis, 2)} − Abschlag {n} Kinder {fmt_pct(ab, 2)} (T_PV_Kinderabschlag)"


def kv_rate_voluntary(s, src, year: int) -> tuple[float, str]:
    satz = src.p("kv_satz_allgemein") if s.options.kv_satz_allgemein else src.p("kv_satz_ermaessigt")
    pv, _, pvtxt = pv_rates(s, src, year)
    total = satz + s.options.kv_zusatz + pv
    txt = (f"KV {fmt_pct(satz, 2)} ({'allgemein' if s.options.kv_satz_allgemein else 'ermäßigt'}) + Zusatzbeitrag "
           f"{fmt_pct(s.options.kv_zusatz, 2)} + {pvtxt} = {fmt_pct(total, 2)}")
    return total, txt


def employee_rate(s, src, year: int) -> float:
    _, pv_an, _ = pv_rates(s, src, year)
    return src.p("kv_satz_allgemein") / 2 + s.options.kv_zusatz / 2 + pv_an


EMPLOYED = ("beschaeftigt", "freigestellt", "neue_beschaeftigung")


def employed_in_month(tl, mi: int) -> bool:
    """Person is employed in the payment month (compulsory insurance, or voluntary above the BBG)."""
    y, m = mi // 12, mi % 12 + 1
    agg = tl.months.get((y, m))
    return bool(agg) and any(agg.days[st] for st in EMPLOYED)


def assessable_payments(tl, ae_payments: list[tuple[int, float]]) -> list[tuple[int, float]]:
    """Ä6 / R_KV_AbfindungPflicht: payments while employed are contribution-free (compulsory insurance) or
    cost nothing extra (voluntary insurance with a salary above the BBG, maximum contribution already paid)."""
    return [(mi, a) for mi, a in ae_payments if not employed_in_month(tl, mi)]


def severance_allocation(ps, tl, s, src, ae_payments: list[tuple[int, float]]) -> dict:
    """Monthly assessment amounts from the severance for voluntary insurance (by month index).
    Only months in which the person is actually voluntarily insured are charged (see build_kv)."""
    mode = s.options.kv_abfindung_mode
    out: dict[int, float] = {}
    ae_payments = assessable_payments(tl, ae_payments)
    total = sum(a for _, a in ae_payments)
    if mode == 1 or total <= 0:
        return out
    if mode == 2:
        if not tl.ruhen158:
            return out
        start = tl.end + ONE
        months = []
        d = start.replace(day=1)
        while d <= tl.fristende:
            months.append(month_index(d.year, d.month))
            d = add_months(d, 1)
        for mi in months:
            out[mi] = out.get(mi, 0.0) + total / len(months)
        return out
    n = int(src.p("kv_abfindung_verteilung_monate"))
    for idx, amount in ae_payments:
        for k in range(n):
            out[idx + k] = out.get(idx + k, 0.0) + amount / n
    return out


def severance_extra(res: KvResult, alloc: dict) -> dict:
    """Extra KV/PV contribution per year caused by the severance allocation ``alloc`` (month index -> amount),
    counted only for days with voluntary insurance (months with ALG or employment drop out)."""
    out: dict[int, float] = {}
    for (y, m), km in res.months.items():
        sev = alloc.get(month_index(y, m), 0.0)
        info = res.vol.get((y, m))
        days = km.days.get("freiwillig", 0)
        if not sev or not info or not days:
            continue
        inc0, lo, hi, rate, mode = info
        frac = days / days_in_month(y, m)
        if mode == "angabe":
            extra = sev * rate
        else:
            extra = (min(max(inc0 + sev, lo), hi) - min(max(inc0, lo), hi)) * rate
        out[y] = out.get(y, 0.0) + extra * frac
    return out


def _severance_trace(ps, idx, s, tracer, rs, tl, ae_payments, res) -> None:
    tb = tracer.new(f"kv_abf_{ps.id}", f"KV-Mehrbeitrag durch die Abfindung {ps.label}", "EUR", f"KV – {ps.label}")
    tb.rule("R_KV_Freiwillig", "R_KV_AbfindungPflicht")
    mode_txt = {1: "nicht verbeitragt", 2: "dem Fristzeitraum zugeordnet", 3: "auf 12 Monate ab Zufluss verteilt"}
    tb.s("options.kv_abfindung_mode", "Abfindung bei freiwilliger Versicherung")
    for mi, a in ae_payments:
        if employed_in_month(tl, mi):
            tb.step(f"Zahlung {mi % 12 + 1:02d}/{mi // 12} ({fmt_eur(a)}) während der Beschäftigung: beitragsfrei bzw. "
                    f"Höchstbeitrag schon erreicht → kein Mehrbeitrag")
        else:
            tb.step(f"Zahlung {mi % 12 + 1:02d}/{mi // 12} ({fmt_eur(a)}) ohne Beschäftigung: "
                    f"{mode_txt[s.options.kv_abfindung_mode]}")
    for y, v in sorted(res.severance_extra.items()):
        tb.step(f"{y}: Mehrbeitrag {fmt_eur(v, 2)} (nur Monate mit freiwilliger Versicherung; Monate mit ALG oder "
                f"Beschäftigung entfallen)")
    total = sum(res.severance_extra.values())
    if not res.severance_extra:
        tb.step("Kein Mehrbeitrag.")
    rs.add(tb.done(total))


def build_kv(ps, idx: int, s, tracer, rs, tl, ae_payments: list[tuple[int, float]], ae_by_year: dict) -> KvResult:
    """``rs`` = None computes without traces (used by the optimiser)."""
    lab = ps.label
    res = KvResult()
    status = ps.kv_status
    prev_pflicht = status in ("pflichtversichert", "unbekannt")
    nachgehend_m = int(tracer.p("kv_nachgehender_anspruch_monate"))
    agentur_ab = int(tracer.p("kv_sperrzeit_agentur_ab_monat"))
    alloc = severance_allocation(ps, tl, s, tracer, ae_payments)
    famgrenze_anteil = tracer.p("kv_famvers_grenze_anteil_bezugsgroesse")
    vorrang = s.options.kv_nachgehend_vorrang

    vol_cache: dict[tuple[int, int], tuple[float, float]] = {}
    calc = s.origin_of(f"persons.{idx}.kv_beitrag_schaetzung") == "abgeleitet"

    def voluntary(y: int, m: int) -> tuple[float, float]:
        key = (y, m)
        if key in vol_cache:
            return vol_cache[key]
        if status == "privat":
            r = (ps.kv_beitrag_schaetzung, 0.0)
        else:
            rate, _ = kv_rate_voluntary(s, tracer, y)
            sev = alloc.get(month_index(y, m), 0.0)
            if not calc:
                base = 0.0
                amount = ps.kv_beitrag_schaetzung + sev * rate
                res.vol[key] = (0.0, 0.0, 0.0, rate, "angabe")
            else:
                inc0 = (ps.capital_for(y)[0] + max(0.0, ps.rent_for(y)[0])) / 12 + ps.kv_sonstige_einnahmen
                lo = tracer.p("kv_mindestbemessung_monat", y)
                hi = tracer.p("kv_bbg_monat", y)
                base = min(max(inc0 + sev, lo), hi)
                amount = base * rate
                res.vol[key] = (inc0, lo, hi, rate, "berechnet")
            r = (amount, base)
        vol_cache[key] = r
        return r

    def family_ok(y: int) -> bool:
        if not s.joint or len(s.persons) < 2 or status == "privat":
            return False
        inc = ps.capital_for(y)[0] + max(0.0, ps.rent_for(y)[0]) + ae_by_year.get(y, 0.0)
        return inc / 12 <= famgrenze_anteil * tracer.p("kv_bezugsgroesse_monat", y)

    emp_rate: dict[int, tuple[float, float]] = {}

    def employee(y: int) -> tuple[float, float]:
        if y not in emp_rate:
            emp_rate[y] = (employee_rate(s, tracer, y), tracer.p("kv_bbg_monat", y))
        return emp_rate[y]

    fam_cache: dict[int, bool] = {}
    E = tl.end
    for d, day in tl.days.items():
        if d.year > s.options.horizon_end:
            break
        km = res.months.setdefault((d.year, d.month), KvMonth())
        dim = days_in_month(d.year, d.month)
        st = day.status
        if st in ("beschaeftigt", "freigestellt", "neue_beschaeftigung"):
            gross = (ps.annual_equiv(d.year) if st != "neue_beschaeftigung" else ps.newjob_salary) / 12
            rate, cap = employee(d.year)
            km.an += min(gross, cap) * rate / dim
            km.days["an"] += 1
            continue
        if st == "alg_bezug":
            km.days["agentur"] += 1
            continue
        k_after = months_between(E + ONE, d)  # 0 = first month after the end of employment
        registered = d >= ps.meldung
        regime = "freiwillig"
        if day.r158:
            regime = "nachgehend" if (prev_pflicht and vorrang and k_after < nachgehend_m) else "freiwillig"
        elif day.sperr and tl.sperr_start:
            k_s = months_between(max(tl.sperr_start, E + ONE), d)
            if k_s >= agentur_ab - 1 and registered:
                regime = "agentur"
            elif prev_pflicht and vorrang and k_after < nachgehend_m:
                regime = "nachgehend"
        elif day.r157 and registered:
            regime = "agentur"
        elif prev_pflicht and vorrang and k_after < nachgehend_m:
            regime = "nachgehend"
        if regime == "freiwillig" and status == "privat":
            regime = "privat"
        if regime == "freiwillig":
            if d.year not in fam_cache:
                fam_cache[d.year] = family_ok(d.year)
            if fam_cache[d.year]:
                regime = "familie"
        km.days[regime] += 1
        if regime in ("freiwillig", "privat"):
            amount, base = voluntary(d.year, d.month)
            km.own += amount / dim
            km.base = base

    res.severance_extra = severance_extra(res, alloc)
    if rs is not None:
        _severance_trace(ps, idx, s, tracer, rs, tl, ae_payments, res)

    # traces per year
    for y in s.years():
        if rs is None:
            break
        tb = tracer.new(f"kv_{ps.id}_{y}", f"Eigene KV/PV-Beiträge {y} {lab}", "EUR", f"KV – {lab}")
        tb.rule("R_KV_ALG", "R_KV_RuhenAbfindung", "R_KV_Freiwillig", "R_KV_AbfindungPflicht", "R_KV_Familie")
        tb.s(f"persons.{idx}.kv_status", "KV-Status vor dem Austritt")
        tb.p("kv_nachgehender_anspruch_monate")
        tb.p("kv_sperrzeit_agentur_ab_monat")
        if status != "privat":
            rate, rtxt = kv_rate_voluntary(s, tb, y)
            if calc:
                tb.child(f"abl_{ps.id}_kvbeitrag")
                tb.p("kv_mindestbemessung_monat", y)
                tb.p("kv_bbg_monat", y)
                tb.step(f"Freiwilliger Beitrag: Einnahmen je Monat (Kapitalerträge {fmt_eur(ps.capital_for(y)[0])}/12, "
                        f"Miete {fmt_eur(max(0.0, ps.rent_for(y)[0]))}/12, sonstige {fmt_eur(ps.kv_sonstige_einnahmen)}"
                        f"{', Abfindungsanteil' if alloc else ''}) zwischen Mindestbemessung und BBG × Satz")
            else:
                tb.s(f"persons.{idx}.kv_beitrag_schaetzung", "Freiwilliger Beitrag je Monat")
            tb.step(f"Beitragssatz: {rtxt}")
            tb.s("options.kv_zusatz", "Zusatzbeitrag")
        mode_txt = {1: "nicht verbeitragt", 2: "dem Fristzeitraum zugeordnet", 3: "auf 12 Monate ab Zufluss verteilt"}
        tb.step(f"Abfindung bei freiwilliger Versicherung: {mode_txt[s.options.kv_abfindung_mode]} (Umschalter); "
                f"Mehrbeitrag siehe „KV-Mehrbeitrag durch die Abfindung“")
        tb.child(f"kv_abf_{ps.id}")
        if ps.newjob and ps.newjob_start.year <= y:
            vpg = tb.p("kv_versicherungspflichtgrenze", y)
            pflicht = ps.newjob_salary < vpg
            tb.step(f"Neue Beschäftigung ab {ps.newjob_start:%d.%m.%Y} ({fmt_eur(ps.newjob_salary)}/Jahr): "
                    + ("pflichtversichert (unter der Versicherungspflichtgrenze " if pflicht else
                       "freiwillig versichert mit Arbeitgeberzuschuss (über der Versicherungspflichtgrenze ")
                    + f"{fmt_eur(vpg)}); Arbeitnehmeranteil auf das Gehalt bis zur BBG")
        own_total = 0.0
        an_total = 0.0
        for mth in range(1, 13):
            km = res.months.get((y, mth))
            if not km:
                continue
            own_total += km.own
            an_total += km.an
            regimes = ", ".join(f"{REGIME_LABEL[r]} {n} T." for r, n in km.days.items())
            extra = f", Bemessung {fmt_eur(km.base)}" if km.own and km.base else ""
            tb.step(f"{fmt_month(y, mth)}: {regimes} → eigener Beitrag {fmt_eur(km.own, 2)}"
                    + (f", AN-Anteil {fmt_eur(km.an, 2)}" if km.an else "") + extra)
        tb.step(f"Summe eigene Beiträge {fmt_eur(own_total, 2)}; Arbeitnehmeranteile {fmt_eur(an_total, 2)} "
                f"(beide als Vorsorgeaufwendungen abziehbar)")
        if not calc or status == "privat":
            tb.flag("unsicher")
        rs.add(tb.done(own_total))
    return res
